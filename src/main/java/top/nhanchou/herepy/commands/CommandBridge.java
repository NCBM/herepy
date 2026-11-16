package top.nhanchou.herepy.commands;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import org.slf4j.Logger;

import com.mojang.brigadier.builder.LiteralArgumentBuilder;
import com.mojang.logging.LogUtils;

import net.minecraft.commands.CommandSourceStack;
import net.minecraft.commands.Commands;
import net.neoforged.bus.api.SubscribeEvent;
import net.neoforged.neoforge.event.RegisterCommandsEvent;
import top.nhanchou.herepy.pythonrt.PythonRunner;

/**
 * The commands units registered, put on the game's dispatcher (ADR 0018).
 *
 * Python owns the behaviour and the ownership; this holds the declarations and rebuilds them whenever the game
 * builds a dispatcher, since a dispatcher lasts one server. Execution goes to the loop and returns at once, which
 * keeps the game thread clear while the unit words its own answer.
 */
public final class CommandBridge {
    private static final Logger LOGGER = LogUtils.getLogger();

    private final PythonRunner python;
    private final Map<String, Integer> declared = new ConcurrentHashMap<>();

    public CommandBridge(PythonRunner python) {
        this.python = python;
    }

    /** One more command: a literal path and the permission level it needs. */
    public void declare(String path, int permission) {
        declared.put(path, permission);
    }

    /** One command gone, because the unit that registered it was revoked or failed. */
    public void withdraw(String path) {
        declared.remove(path);
    }

    @SubscribeEvent
    public void onRegisterCommands(RegisterCommandsEvent event) {
        Map<String, Integer> snapshot = Map.copyOf(declared);
        if (snapshot.isEmpty()) {
            return;
        }
        snapshot.forEach((path, permission) -> event.getDispatcher().register(chain(path, permission)));
        LOGGER.info("Commands declared by units: {}", snapshot.keySet());
    }

    /**
     * One literal path as a Brigadier chain.
     *
     * The permission sits on the first literal only: every path a unit registers is its own root, so requiring it
     * once is enough, and a shared root merges with the other paths under it.
     */
    private LiteralArgumentBuilder<CommandSourceStack> chain(String path, int permission) {
        List<String> parts = List.of(path.split(" "));
        List<LiteralArgumentBuilder<CommandSourceStack>> builders = new ArrayList<>(parts.size());
        for (String part : parts) {
            builders.add(Commands.literal(part));
        }
        builders.getFirst().requires(source -> source.hasPermission(permission));
        // `then` builds the child it is handed, so the deepest literal is given its command before it is attached.
        builders.getLast().executes(context -> {
            python.submit("commands.run", path, context.getSource());
            return 1;
        });
        for (int i = 0; i + 1 < builders.size(); i++) {
            builders.get(i).then(builders.get(i + 1));
        }
        return builders.getFirst();
    }
}
