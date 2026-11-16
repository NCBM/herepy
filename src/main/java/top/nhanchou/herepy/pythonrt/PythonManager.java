package top.nhanchou.herepy.pythonrt;

import java.io.File;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import org.slf4j.Logger;

import com.mojang.logging.LogUtils;

/**
 * Where the embedded runtime's files are (ADR 0014), read from the tree rather than from the machine (ADR 0016).
 *
 * The runtime has two layouts and they share no path. POSIX: {@code lib/libpython3.13.so},
 * {@code lib/python3.13/}, {@code lib/python3.13/site-packages/jep/libjep.so}. Windows: {@code python313.dll},
 * {@code Lib/}, {@code Lib/site-packages/jep/jep.dll}. The mod has to find either, so the question asked below is
 * never "which OS is this" but "which tree is this": a {@code python.exe} or a {@code python3NN.dll} means the
 * Windows layout, and the rest follows from what is on disk. That is also what makes this checkable without
 * Windows — the tree the build produces is a Windows tree, and a Windows JVM under Wine reads it the same way.
 */
public final class PythonManager {

    private static final Logger LOGGER = LogUtils.getLogger();
    private static final String osName = System.getProperty("os.name");
    private static final String osVersion = System.getProperty("os.version");

    static {
        if (osName == null) {
            throw new RuntimeException("Cannot get operating system name.");
        }
        if (osVersion == null) {
            throw new RuntimeException("Cannot get operating system version.");
        }
        if (osName.contains("Windows") && Double.parseDouble(osVersion) < 10) {
            LOGGER.warn(
                    "Your system version is lower than Windows 10, thus running this mod may came to error. We are not responsible for this kind of issues.");
        }
    }

    private PythonManager() {
    }

    /** The runtime's root: {@code python/} in the working directory, or whatever {@code PYTHON_HOME} names. */
    public static String getPythonHome() {
        return home().getAbsolutePath();
    }

    /**
     * jep's native half, under the name this process loads it by.
     *
     * jep builds one binary twice — the CPython extension ({@code jep.pyd}, {@code jep.cpython-313-*.so}) and the
     * library a JVM loads ({@code jep.dll}, {@code libjep.so}, {@code libjep.dylib}) — and this is the second
     * one. On Windows it is neither {@code libjep.pyd} nor the name the extension has (ADR 0016).
     */
    public static String getJepLibPath() {
        File home = home();
        File jep = new File(moduleRoot(home), "site-packages/jep");
        List<String> names = windowsLayout(home) ? List.of("jep.dll") : List.of("libjep.dylib", "libjep.so");
        for (String name : names) {
            File candidate = new File(jep, name);
            if (candidate.isFile()) {
                return candidate.getAbsolutePath();
            }
        }
        throw new IllegalStateException("Cannot find jep's native library: no " + names + " in " + jep
                + ", and a runtime without it cannot start Python at all (ADR 0011).");
    }

    /**
     * The interpreter itself, as a file to hand to {@link System#load}.
     *
     * jep's native half needs libpython by soname, and the dev run used to get it from {@code LD_PRELOAD} in
     * the Gradle run config — which a player cannot set. Loading it from Java is the same thing done by the
     * process that needs it, and it is the one fix that reads the same on all three platforms (ADR 0015).
     */
    public static String getPythonSharedLibrary() {
        File home = home();
        String version = minorVersion(home);
        List<String> names = windowsLayout(home)
                ? List.of("python" + version.replace(".", "") + ".dll")
                : List.of("lib/libpython" + version + ".dylib", "lib/libpython" + version + ".so.1.0",
                        "lib/libpython" + version + ".so");
        for (String name : names) {
            File candidate = new File(home, name);
            if (candidate.isFile()) {
                return candidate.getAbsolutePath();
            }
        }
        throw new IllegalStateException("Cannot find the Python shared library: no " + names + " in " + home);
    }

    /** The {@code 3.13} of the interpreter in this runtime. */
    public static String getPythonMinorVersion() {
        return minorVersion(home());
    }

    private static File home() {
        File local = new File("python");
        if (local.isDirectory()) {
            return local.getAbsoluteFile();
        }
        String configured = System.getenv("PYTHON_HOME");
        if (configured != null && !configured.isBlank()) {
            File given = new File(configured);
            if (given.isDirectory()) {
                return given.getAbsoluteFile();
            }
            throw new IllegalStateException(
                    "PYTHON_HOME is " + given.getAbsolutePath() + ", which is not a directory");
        }
        throw new IllegalStateException("No Python runtime to start: " + local.getAbsolutePath()
                + " is not a directory and PYTHON_HOME is unset. Unpack the pinned runtime as 'python/' beside"
                + " the game (ADR 0014).");
    }

    /**
     * {@code python.exe} or a {@code python3NN.dll} — the two names the Windows layout has and no POSIX tree ever
     * does. Not {@code Lib/}: NTFS and APFS both fold case, so {@code Lib} and {@code lib} are the same name
     * there, and asking for one is asking for the other.
     */
    private static boolean windowsLayout(File home) {
        if (new File(home, "python.exe").isFile()) {
            return true;
        }
        for (File entry : list(home)) {
            if (entry.getName().matches("python3\\d+\\.dll")) {
                return true;
            }
        }
        return false;
    }

    private static File moduleRoot(File home) {
        File root = new File(home, windowsLayout(home) ? "Lib" : "lib/python" + minorVersion(home));
        if (!root.isDirectory()) {
            throw new IllegalStateException("Cannot find the Python standard library: " + root
                    + " is not a directory");
        }
        return root;
    }

    /**
     * The minor version, from the name that carries it: {@code python313.dll} beside the interpreter, or the
     * {@code python3.13/} directory that is the standard library.
     */
    private static String minorVersion(File home) {
        boolean windows = windowsLayout(home);
        Pattern pattern = windows ? Pattern.compile("python3(\\d+)\\.dll") : Pattern.compile("python3\\.(\\d+)");
        File directory = windows ? home : new File(home, "lib");
        int minor = -1;
        for (File entry : list(directory)) {
            if (!windows && !entry.isDirectory()) {
                continue;
            }
            Matcher matcher = pattern.matcher(entry.getName());
            if (matcher.matches()) {
                minor = Math.max(minor, Integer.parseInt(matcher.group(1)));
            }
        }
        if (minor < 0) {
            throw new IllegalStateException("Cannot tell which Python " + directory + " holds: no entry matches "
                    + pattern.pattern());
        }
        return "3." + minor;
    }

    /** The entries of a directory, or none when it is not one: every caller here reports what is missing. */
    private static List<File> list(File directory) {
        File[] entries = directory.listFiles();
        return entries == null ? List.of() : List.of(entries);
    }
}
