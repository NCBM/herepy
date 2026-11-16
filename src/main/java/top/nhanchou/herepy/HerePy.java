package top.nhanchou.herepy;

import java.util.concurrent.TimeUnit;

import org.slf4j.Logger;

import com.mojang.logging.LogUtils;

import jep.Interpreter;
import jep.MainInterpreter;
import jep.PyConfig;
import net.minecraft.core.BlockPos;
import net.minecraft.network.chat.Component;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.server.MinecraftServer;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.level.Level;
import net.minecraft.world.phys.Vec3;
import net.neoforged.bus.api.IEventBus;
import net.neoforged.fml.loading.FMLEnvironment;
import net.neoforged.fml.loading.FMLPaths;
import net.neoforged.fml.common.Mod;
import net.neoforged.neoforge.common.NeoForge;
import top.nhanchou.herepy.commands.CommandBridge;
import top.nhanchou.herepy.event.EventBridge;
import top.nhanchou.herepy.pythonrt.PythonManager;
import top.nhanchou.herepy.pythonrt.PythonRunner;
import top.nhanchou.herepy.reflective.ReflectWrapper;

// The value here should match an entry in the META-INF/neoforge.mods.toml file
@Mod(HerePy.MODID)
public class HerePy {
    // Define mod id in a common place for everything to reference
    public static final String MODID = "herepy";
    public static final Logger LOGGER = LogUtils.getLogger();

    public PythonRunner pythonRunner;
    private EventBridge eventBridge;
    private CommandBridge commandBridge;

    // The constructor for the mod class is the first code that is run when your mod is loaded.
    // FML recognizes some parameter types like IEventBus and passes them in automatically.
    public HerePy(IEventBus modEventBus) {
        PyConfig config = PyConfig.python();

        try {
            config.setHome(PythonManager.getPythonHome());
            MainInterpreter.setJepLibraryPath(PythonManager.getJepLibPath());
            MainInterpreter.setInitParams(config);
            // Load the interpreter ourselves before jep looks for it: libjep.so needs libpython by soname, and
            // a player's machine has no LD_PRELOAD to offer (ADR 0015). On Windows the same call is what makes
            // jep.dll's python313.dll import resolve — a DLL the process already has is one the loader will not
            // go looking for. The dev run used to get this from the Gradle run config; now it comes from the
            // process that needs it.
            System.load(PythonManager.getPythonSharedLibrary());
            pythonRunner = new PythonRunner();
            eventBridge = new EventBridge(pythonRunner, modEventBus);
            commandBridge = new CommandBridge(pythonRunner);
            pythonRunner.start(this::bootstrapPython);
            // Loading runs on the host thread while this one carries on, so this wait is what puts the units in
            // place before the server starts (ADR 0018). A slow bootstrap is reported and the game moves on.
            if (!pythonRunner.awaitReady(60, TimeUnit.SECONDS)) {
                LOGGER.warn("The Python units did not finish loading within 60 s; the game continues without them");
            }
        } catch (Exception e) {
            LOGGER.error("Cannot start python interpreter for mod '{}'.", MODID, e);
            throw e;
        }
        NeoForge.EVENT_BUS.register(commandBridge);
    }

    /**
     * Everything Python needs before the loop starts, and then the loop itself.
     *
     * Runs on the host thread with the interpreter that thread created, and does not return until the
     * mod is shutting down: its last call is the loader, which ends by handing the thread to the loop
     * (ADR 0009). A failure here is reported by {@link PythonRunner} rather than thrown, because it
     * happens on no caller's stack.
     */
    private void bootstrapPython(Interpreter interpreter) {
        // Say which interpreter this is. The runtime is a pinned artifact (ADR 0014), so a bug report
        // should show whether the pin is what ran.
        interpreter.exec("import sys");
        LOGGER.info(
                "Python {} from {}",
                interpreter.getValue("sys.version.split()[0]", String.class),
                PythonManager.getPythonHome());

        // The distribution and the game directory, before anything can ask which they are: closed values that
        // arrive as strings and become a Python enum and a `Path`, so a unit reads typed values rather than JEP
        // proxies (ADR 0017). The module is bound under its own name because that is what `invoke` resolves.
        interpreter.exec("import herecraft.env as env");
        interpreter.invoke("env.install", FMLEnvironment.dist.name(), FMLPaths.GAMEDIR.get().toString());

        // Route Python's logging to SLF4J before anything can log. Without this the only
        // handler left is Python's last-resort one, which drops everything below WARNING --
        // that is every message the loader reports.
        interpreter.exec("import herecraft.logging");
        interpreter.exec("import herecraft.conversions");
        interpreter.exec("from herecraft._internals import javans");
        interpreter.invoke("javans.inject", "ReflectWrapper", ReflectWrapper.class);
        interpreter.invoke("javans.inject", "PythonRunner", PythonRunner.class);

        // Bootstrap Pythonic API wrappers
        interpreter.exec("from herecraft.api._setup import _bootstrap");
        interpreter.invoke("_bootstrap",
            BlockPos.class,
            Vec3.class,
            ResourceLocation.class,
            Component.class,
            net.minecraft.world.item.ItemStack.class,
            Level.class,
            MinecraftServer.class,
            Entity.class,
            Player.class
        );

        // Hand Python the bus before any unit loads: a unit's @event handler registers with
        // this bridge as the unit makes it, and needs somewhere to put it (ADR 0006).
        interpreter.exec("from herecraft.kernel import install_bridge");
        interpreter.invoke("install_bridge", eventBridge);

        // The other direction of the same seam: the commands units registered, which the game asks for whenever
        // it builds a dispatcher (ADR 0018). Bound by name, because `invoke` resolves against these globals.
        interpreter.exec("from herecraft.commands import install_commands");
        interpreter.invoke("install_commands", commandBridge);

        // Bind the seam under a short name: every crossing from Java names it as `_host.<entry>`, and
        // a thread other than this one reaches the same globals through an attached view. Two dotted
        // parts, because that is what jep's invoke resolves — three is not a name it can look up.
        interpreter.exec("import herecraft.kernel.host as _host");

        // Load the units in mods/ and enable them, then serve the loop until shutdown: the phase table of
        // ADR 0018, and the last thing this thread does. `pythonRunner` goes with it so the load can say when
        // it is done, and the mod can wait for that before the game moves on.
        interpreter.exec("import herecraft.kernel.boot as boot");
        interpreter.invoke("boot.start", pythonRunner);
    }
}