package top.nhanchou.herepy.pythonrt;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import java.util.function.Consumer;

import org.slf4j.Logger;

import com.mojang.logging.LogUtils;

import jep.Interpreter;
import jep.SharedInterpreter;

/**
 * The Python host thread, and the loop it serves (ADR 0009).
 *
 * One thread owns the interpreter and an asyncio event loop for the whole of its life, so
 * "single-threaded interpreter" now means "single loop": work reaches the loop by name through
 * {@code herecraft.kernel.host} and runs there, and the thread that handed it over is never the one
 * that ran it.
 *
 * jep binds an {@link Interpreter} to the thread that made it, so a caller on any other thread gets
 * its own view with {@link Interpreter#attach}. The view that shares {@code __main__} is
 * {@code attach(true)}; {@code attach(false)} shares the interpreter's state but not its globals, and
 * can therefore not resolve the seam. One view is kept per calling thread, because attaching is not
 * free and a thread that crosses once crosses again.
 */
public class PythonRunner {
    private static final Logger LOGGER = LogUtils.getLogger();

    /** The module the crossings are named in, as the bootstrap binds it: {@code submit}, {@code call_sync}, {@code stop}. */
    private static final String SEAM = "_host";

    /** The interpreter the host thread created, or null while there is none to call into. */
    private final AtomicReference<SharedInterpreter> serving = new AtomicReference<>();

    /** The view each calling thread uses, made on first use on that thread. */
    private final ThreadLocal<Interpreter> callers = new ThreadLocal<>();

    /** Counted down once every unit is loaded and enabled, so the mod can wait for that (ADR 0018). */
    private final CountDownLatch ready = new CountDownLatch(1);

    private Thread thread;
    private volatile boolean closed;

    /**
     * Start the host thread and hand it {@code init}, which runs before the loop and ends by waiting
     * for the loop to stop.
     *
     * The interpreter is created on the thread that owns it, configured by {@code init}, and closed
     * by that same thread when {@code init} returns; a failure there is reported rather than thrown,
     * because it happens on no caller's stack.
     */
    public synchronized void start(Consumer<Interpreter> init) {
        if (thread != null) {
            throw new IllegalStateException("The Python host thread is already started.");
        }
        thread = new Thread(() -> run(init), "herecraft-python");
        // Nothing joins this thread at shutdown, so it may not be what keeps the JVM alive: the loop
        // stops when close() is called, and a mod whose loader never calls it should still exit.
        thread.setDaemon(true);
        thread.start();
    }

    /**
     * Hand {@code target}, one of the seam's names, to the loop; answer without waiting for it.
     *
     * A failure of the work is reported by the seam on the loop, with the target's name, rather than
     * thrown here: nobody on this side is waiting for an answer to throw it to.
     */
    public void submit(String target, Object... args) {
        view().invoke(SEAM + ".submit", arguments(target, args));
    }

    /**
     * Hand {@code target} to the loop and wait for its answer, no longer than the seam's deadline.
     *
     * A {@code null} answer is the deadline: the work was cancelled and the answer counts as none.
     * That is the seam's policy and is decided there, so every synchronous crossing pays the same one
     * (ADR 0009).
     */
    public Object callSync(String target, Object... args) {
        return view().invoke(SEAM + ".call_sync", arguments(target, args));
    }

    /**
     * Note that every unit is loaded and enabled.
     *
     * The bootstrap calls this through Python after the last unit has been handed to the bus and before the loop
     * takes the thread. It is the only caller, so a bootstrap that fails leaves the wait to time out.
     */
    public void markReady() {
        ready.countDown();
    }

    /**
     * Wait until the units are loaded, or the deadline passes.
     *
     * Loading runs on the host thread while the game's own thread carries on, so without waiting here the
     * server can start before a unit has registered its server lifecycle handler — which is the one thing
     * that handler is for (ADR 0018). A {@code false} answer is a slow bootstrap, not a failure: the game
     * keeps going without what has not arrived.
     */
    public boolean awaitReady(long timeout, TimeUnit unit) {
        try {
            return ready.await(timeout, unit);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            return false;
        }
    }

    /** Stop the loop, and the host thread with it; the interpreter is closed on its own thread. */
    public void close() {
        if (closed || thread == null) {
            return;
        }
        closed = true;
        if (serving.get() != null) {
            try {
                view().invoke(SEAM + ".stop");
            } catch (RuntimeException e) {
                LOGGER.warn("Asking the Python loop to stop failed", e);
            }
        }
        try {
            thread.join(5000);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            return;
        }
        if (thread.isAlive()) {
            LOGGER.warn("The Python host thread did not stop within 5 s");
        }
    }

    private void run(Consumer<Interpreter> init) {
        SharedInterpreter primary = new SharedInterpreter();
        serving.set(primary);
        LOGGER.debug("Python host thread is up");
        try {
            init.accept(primary);
        } catch (Throwable t) {
            LOGGER.error("The Python host thread failed", t);
        } finally {
            serving.set(null);
            try {
                primary.close();
            } catch (RuntimeException e) {
                LOGGER.warn("Closing the Python interpreter failed", e);
            }
            LOGGER.debug("Python host thread is down");
        }
    }

    /** This thread's way into the interpreter, made on first use and kept afterwards. */
    private Interpreter view() {
        Interpreter view = callers.get();
        if (view != null) {
            return view;
        }
        SharedInterpreter primary = serving.get();
        if (primary == null || closed) {
            throw new IllegalStateException(
                    "The Python host thread is not serving, so nothing can be handed to it: no Python"
                            + " call can happen before it starts, because no listener exists before that.");
        }
        view = primary.attach(true);
        callers.set(view);
        return view;
    }

    private static Object[] arguments(String target, Object[] args) {
        Object[] all = new Object[args.length + 1];
        all[0] = target;
        System.arraycopy(args, 0, all, 1, args.length);
        return all;
    }
}
