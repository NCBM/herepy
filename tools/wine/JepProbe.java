/**
 * The Windows target's smoke test (ADR 0016): a Windows JVM under Wine loads a jep built with MSVC, starts the
 * materialized Windows runtime, and reaches numpy.
 *
 * Arguments, all Windows-style paths: the jep library to load, the runtime's home, and the runtime's
 * python313.dll. Nothing here is game-shaped: it is `runClient` minus the game.
 */
import jep.MainInterpreter;
import jep.PyConfig;
import jep.SharedInterpreter;

public class JepProbe {
    public static void main(String[] args) throws Exception {
        String jepLibrary = args[0];
        String runtimeHome = args[1];
        String pythonLibrary = args[2];

        // The same trick the mod uses for its own loads: bring the interpreter in first, so jep's own NEEDED
        // entry is satisfied by a library the process already has.
        System.load(pythonLibrary);
        MainInterpreter.setJepLibraryPath(jepLibrary);
        PyConfig config = PyConfig.python();
        config.setHome(runtimeHome);
        MainInterpreter.setInitParams(config);

        try (SharedInterpreter interp = new SharedInterpreter()) {
            interp.exec("import sys");
            System.out.println("python : " + interp.getValue("sys.version.split()[0]", String.class));
            System.out.println("prefix : " + interp.getValue("sys.prefix", String.class));
            interp.exec("import numpy as np");
            System.out.println("numpy  : " + interp.getValue("np.__version__", String.class));
            System.out.println("sum    : " + interp.getValue("float(np.arange(10).sum())", Double.class));

            // How much of the mod's Python half starts without the game on the classpath: this is what a Wine
            // boot can reach, and what it reports is what is missing for a real one (ADR 0016).
            for (String step : new String[] {"import herecraft", "import herecraft.kernel.host",
                    "import herecraft.event", "import herecraft.api.events"}) {
                try {
                    interp.exec(step);
                    System.out.println("boot   : " + step + " ok");
                } catch (Exception failure) {
                    String message = String.valueOf(failure.getMessage()).split("\n")[0];
                    System.out.println("boot   : " + step + " failed: " + message);
                }
            }
        }
        System.out.println("probe ok");
    }
}
