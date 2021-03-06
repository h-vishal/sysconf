"""
Support library which provides utiliy functions in case I'll
ever want to do logic in python instead of bash, or in case
I want bash to use Python.

Import it as "from sysconf import something"
"""

import contextlib
import errno
import functools
import os
import shutil
import subprocess
import sys
import tempfile


PYTHON = sys.executable
HERE = os.path.abspath(os.path.dirname(__file__))
PY3 = sys.version_info[0] == 3


# =============================================================================
# --- path constants
# =============================================================================


DIR_ROOT = HERE
DIR_BIN = os.path.join(DIR_ROOT, 'bin')
DIR_STATIC = os.path.join(DIR_ROOT, 'static')
DIR_STATIC_HOME = os.path.join(DIR_ROOT, 'static/home')
DIR_HOME = os.path.expanduser("~")


# =============================================================================
# --- OS constants
# =============================================================================


POSIX = os.name == "posix"
WINDOWS = os.name == "nt"
LINUX = sys.platform.startswith("linux")
OSX = sys.platform.startswith("darwin")
FREEBSD = sys.platform.startswith("freebsd")
OPENBSD = sys.platform.startswith("openbsd")
NETBSD = sys.platform.startswith("netbsd")
BSD = FREEBSD or OPENBSD or NETBSD
SUNOS = sys.platform.startswith("sunos") or sys.platform.startswith("solaris")


# =============================================================================
# --- utils
# =============================================================================


class SkipTask(Exception):
    pass


def memoize(f):
    """Memoize function or method return values, saving time if
    method has already been called with that same argument.
    """
    cache = {}

    def memf(*x):
        if x not in cache:
            cache[x] = f(*x)
        return cache[x]
    return memf


@memoize
def _term_supports_colors(file=sys.stdout):
    try:
        import curses
        assert file.isatty()
        curses.setupterm()
        assert curses.tigetnum("colors") > 0
    except Exception:
        return False
    else:
        return True


def hilite(s, ok=True, bold=False):
    """Return an highlighted version of 'string'."""
    if not _term_supports_colors():
        return s
    attr = []
    if ok is None:  # no color
        pass
    elif ok:   # green
        attr.append('32')
    else:   # red
        attr.append('31')
    if bold:
        attr.append('1')
    return '\x1b[%sm%s\x1b[0m' % (';'.join(attr), s)


def log(prefix, s=None):
    if not s:
        print(hilite(s))
    else:
        print("%-20s: %s" % (hilite(prefix), s))


def logerr(prefix, s=None):
    if not s:
        print(hilite(s, ok=False))
    else:
        print("%s: %s" % (hilite(prefix, ok=False), s))


def logtitle(s):
    print(hilite("\n>>> %s <<<\n" % s, bold=True))


def skip_if(condition=None, msg=None):
    """Decorator to skip function execution."""
    def decorator(fun):
        @functools.wraps(fun)
        def wrapper(*args, **kwargs):
            if condition:
                log("skip", msg or " ")
            else:
                return fun(*args, **kwargs)
        return wrapper
    return decorator


# =============================================================================
# --- shell
# =============================================================================


def sh(cmd, sudo=False):
    """run cmd in a subprocess; exit on error."""
    if sudo:
        if os.geteuid() != 0 and which('sudo'):
            cmd = 'sudo ' + cmd
    log("sh", cmd)
    code = os.system(cmd)
    if code != 0:
        logerr('sh', 'cmd failed (code=%s); exiting interprter' % code)
        raise SystemExit


def pyrun(src):
    """Run python code 'src' in a separate interpreter.
    Return interpreter subprocess.
    """
    if PY3:
        src = bytes(src, 'ascii')
    with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as f:
        f.write(src)
        f.flush()
        return subprocess.check_output(["sudo", PYTHON, f.name])


try:
    from shutil import which
except ImportError:
    def which(cmd, mode=os.F_OK | os.X_OK, path=None):
        """Given a command, mode, and a PATH string, return the path which
        conforms to the given mode on the PATH, or None if there is no such
        file.

        `mode` defults to os.F_OK | os.X_OK. `path` defults to the result
        of os.environ.get("PATH"), or can be overridden with a custom search
        path.
        """
        def _access_check(fn, mode):
            return (os.path.exists(fn) and os.access(fn, mode) and
                    not os.path.isdir(fn))

        if os.path.dirname(cmd):
            if _access_check(cmd, mode):
                return cmd
            return None

        if path is None:
            path = os.environ.get("PATH", os.defpath)
        if not path:
            return None
        path = path.split(os.pathsep)

        if sys.platform == "win32":
            if os.curdir not in path:
                path.insert(0, os.curdir)

            pathext = os.environ.get("PATHEXT", "").split(os.pathsep)
            if any(cmd.lower().endswith(ext.lower()) for ext in pathext):
                files = [cmd]
            else:
                files = [cmd + ext for ext in pathext]
        else:
            files = [cmd]

        seen = set()
        for dir in path:
            normdir = os.path.normcase(dir)
            if normdir not in seen:
                seen.add(normdir)
                for thefile in files:
                    name = os.path.join(dir, thefile)
                    if _access_check(name, mode):
                        return name
        return None


def install_pkg(*names):
    if LINUX:
        names = ' '.join(names)
        sh("apt-get install -y %s" % names, sudo=True)
    else:
        raise NotImplementedError


def uninstall_pkg(*names):
    if LINUX:
        names = ' '.join(names)
        sh("apt-get purge -y %s" % names, sudo=True)
        sh("apt-get autoremove -y", sudo=True)
    else:
        raise NotImplementedError


# =============================================================================
# --- fs utils
# =============================================================================


def symlink(source, linkname):
    log("symlink", "%s -> %s" % (source, linkname))
    os.symlink(source, linkname)


def copy(src, dst):
    parent = os.path.dirname(dst)
    if parent:
        safe_makedirs(parent)
    log("cp (file)", "%s -> %s" % (src, dst))
    shutil.copy(src, dst)


def copydir(src, dst):
    parent = os.path.dirname(dst)
    if parent:
        safe_makedirs(parent)
    log("cp (dir)", "%s -> %s" % (src, dst))
    shutil.copytree(src, dst)


def safe_remove(path):
    "Same as os.remove() but doesn't raise exception on missing file"
    try:
        os.remove(path)
    except OSError as err:
        if err.errno != errno.ENOENT:
            raise
    else:
        log("rm", path)


def safe_makedirs(path, mode=None):
    "Same as os.makedirs() but doesn't raise exception if dir already exists"
    log("mkdir -p", path)
    try:
        os.makedirs(path, **dict(mode=mode) if mode is not None else {})
    except OSError as err:
        if err.errno == errno.EEXIST:
            if not os.path.isdir(path):
                raise
            elif mode is not None:
                os.chmod(path, mode)
        else:
            raise


def safe_rmtree(path):
    "Same as shutil.rmtree but doesn't raise exception if path does not exist"
    log("rmtree", path)

    def onerror(fun, path, excinfo):
        exc = excinfo[1]
        if exc.errno != errno.ENOENT:
            raise

    shutil.rmtree(path, onerror=onerror)


def safe_rmpath(path):
    """Removes a path either if it's a file or a directory.
    If neither exist just do nothing.
    """
    if os.path.isdir(path):
        safe_rmtree(path)
    else:
        safe_remove(path)


def touch(name):
    """Create a file and return its name."""
    log("touch", name)
    parent = os.path.dirname(name)
    if parent:
        safe_makedirs(parent)
    with open(name, 'w') as f:
        return f.name


@contextlib.contextmanager
def cwd(path):
    cur_dir = os.getcwd()
    try:
        os.chdir(path)
        yield
    finally:
        os.chdir(cur_dir)


# =============================================================================
# --- network
# =============================================================================


def wget(url, file):
    sh('wget --no-check-certificate %s -O "%s" ' % (url, file))


# =============================================================================
# --- sys
# =============================================================================


def is_x_running():
    if not which('xset'):
        return False
    p = subprocess.Popen(["xset", "-q"],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    p.communicate()
    return p.returncode == 0
