package top.nhanchou.herepy.event;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.function.Consumer;

import org.slf4j.Logger;

import com.mojang.logging.LogUtils;

import net.neoforged.bus.api.Event;
import net.neoforged.bus.api.ICancellableEvent;
import net.neoforged.bus.api.IEventBus;
import net.neoforged.fml.loading.FMLEnvironment;
import net.neoforged.neoforge.common.NeoForge;
import top.nhanchou.herepy.pythonrt.PythonRunner;

/**
 * Bridges NeoForge event buses to the Python handlers registered through herecraft.event.
 *
 * Python calls {@link #retain} once per handler and {@link #release} when a handler is revoked. One
 * event class gets one listener object however many units listen to it, so the count is kept here:
 * the listener goes up when the first unit asks and comes down when the last one stops. The object
 * the bus was given is the one kept, because {@code IEventBus.unregister} takes back by identity —
 * dismissing a lambda nobody kept is what left registrations unrevocable (ADR 0006).
 *
 * Dispatch hands the event to the Python loop by the name it is registered under there (ADR 0009):
 * an event with no cancellable handler is answered at once, and one with a cancellable handler waits
 * for the loop's answer under a deadline.
 */
public class EventBridge {
    private static final Logger LOGGER = LogUtils.getLogger();

    /** The entries {@code herecraft.kernel.host} holds for the two halves of a dispatch. */
    private static final String DISPATCH = "event.dispatch";
    private static final String DISPATCH_SYNC = "event.dispatch_sync";


    private final PythonRunner pythonRunner;
    private final IEventBus modEventBus;

    /** One listener per event class, keyed by the Java class name Python registered under. */
    private final Map<String, Trigger> triggers = new ConcurrentHashMap<>();

    public EventBridge(PythonRunner pythonRunner, IEventBus modEventBus) {
        this.pythonRunner = pythonRunner;
        this.modEventBus = modEventBus;
    }

    /**
     * One more unit listens to this event class; the bus gets a listener if it had none.
     *
     * A handler that has to run synchronously is dispatched inline, and a listener that was put up
     * for asynchronous handlers only is replaced by one that dispatches inline as well: the listener
     * a class has is the union of what its handlers need, so it can only ever grow that way.
     */
    public synchronized void retain(String javaClassName, boolean needsSync) {
        Trigger trigger = triggers.get(javaClassName);
        if (trigger == null) {
            trigger = new Trigger(busFor(javaClassName), eventType(javaClassName), needsSync);
            attach(trigger);
            triggers.put(javaClassName, trigger);
            LOGGER.info("Python listener for {} is up ({})", javaClassName, needsSync ? "sync" : "async");
            return;
        }
        trigger.bindings++;
        if (needsSync && !trigger.sync) {
            Trigger synchronous = new Trigger(trigger.bus, trigger.type, true);
            synchronous.bindings = trigger.bindings;
            detach(trigger);
            attach(synchronous);
            triggers.put(javaClassName, synchronous);
            LOGGER.info("Python listener for {} now dispatches synchronously", javaClassName);
        }
    }

    /** One fewer unit listens to this event class; the last one takes the bus's listener with it. */
    public synchronized void release(String javaClassName) {
        Trigger trigger = triggers.get(javaClassName);
        if (trigger == null) {
            LOGGER.warn("Nothing to release for {}: no Python listener is held for it", javaClassName);
            return;
        }
        trigger.bindings--;
        if (trigger.bindings > 0) {
            return;
        }
        triggers.remove(javaClassName);
        detach(trigger);
        LOGGER.info("Python listener for {} is down", javaClassName);
    }

    /**
     * One listener object, and the bus it belongs to.
     *
     * This object is what {@code addListener} is given and therefore what {@code unregister} gets
     * back: the bus stores consumers under the consumer itself, so keeping it is the whole of being
     * able to remove exactly one listener.
     */
    private final class Trigger implements Consumer<Event> {
        private final IEventBus bus;
        private final Class<? extends Event> type;
        private final boolean sync;
        private int bindings = 1;

        private Trigger(IEventBus bus, Class<? extends Event> type, boolean sync) {
            this.bus = bus;
            this.type = type;
            this.sync = sync;
        }

        @Override
        public void accept(Event event) {
            if (sync) {
                dispatchSync(event);
            } else {
                dispatchAsync(event);
            }
        }
    }

    @SuppressWarnings({ "unchecked", "rawtypes" })
    private static void attach(Trigger trigger) {
        // The bus takes the class and the consumer as one type variable; the trigger was built from
        // exactly that pair, so the raw call is what says so without inventing a second object.
        trigger.bus.addListener((Class) trigger.type, trigger);
    }

    private static void detach(Trigger trigger) {
        trigger.bus.unregister(trigger);
    }

    private static Class<? extends Event> eventType(String javaClassName) {
        Class<?> type;
        try {
            type = Class.forName(javaClassName);
        } catch (ClassNotFoundException e) {
            // A name that is not on this classpath is either a typo or an event that only exists where there is
            // a client. Saying which distribution this is turns the second case into a sentence (ADR 0017).
            throw new IllegalArgumentException(
                    "No class named " + javaClassName + " on this distribution (" + FMLEnvironment.dist
                            + "): either the name is wrong, or the class exists only where there is a client.",
                    e);
        }
        if (!Event.class.isAssignableFrom(type)) {
            throw new IllegalArgumentException(javaClassName + " is not a NeoForge Event");
        }
        return type.asSubclass(Event.class);
    }

    /**
     * Choose which event bus a listener belongs on, from the event class's package.
     * FML lifecycle events go on the mod event bus; game events go on the forge bus.
     */
    private IEventBus busFor(String javaClassName) {
        if (javaClassName.startsWith("net.neoforged.fml.event.")) {
            return modEventBus;
        }
        return NeoForge.EVENT_BUS;
    }

    private void dispatchAsync(Event event) {
        try {
            pythonRunner.submit(DISPATCH, event);
        } catch (RuntimeException e) {
            // A dispatch that cannot be handed over is reported here and not thrown into the bus,
            // where it would take the caller down with it.
            LOGGER.error("Dispatching {} to Python failed", event.getClass().getName(), e);
        }
    }

    /**
     * Let the cancellable handlers decide, and wait for that decision under the seam's deadline.
     *
     * The asynchronous handlers for the same event run first and nobody waits for them, which is the
     * order the two lists were dispatched in before the loop existed. An answer of {@code null} is a
     * dispatch that ran out of time: the event goes on uncancelled and the seam has already reported
     * which one and how long it waited, so a stall costs ticks and does not cost the log twice.
     */
    private void dispatchSync(Event event) {
        Object answer;
        try {
            pythonRunner.submit(DISPATCH, event);
            answer = pythonRunner.callSync(DISPATCH_SYNC, event);
        } catch (RuntimeException e) {
            LOGGER.error("Dispatching {} to Python failed", event.getClass().getName(), e);
            return;
        }
        if (Boolean.TRUE.equals(answer) && event instanceof ICancellableEvent cancelable) {
            cancelable.setCanceled(true);
            LOGGER.debug("Python handler canceled event {}", event.getClass().getName());
        }
    }
}
