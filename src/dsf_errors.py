class Error(Exception):
    pass

class ErrorOk(Error):
    pass

class ErrorCouldNotOpenFile(Error):
    pass

class ErrorCouldNotReadFile(Error):
    pass

class ErrorNoAtoms(Error):
    pass

class ErrorBadCookie(Error):
    pass

class ErrorBadVersion(Error):
    pass

class ErrorMissingAtom(Error):
    pass

class ErrorBadProperties(Error):
    pass

class ErrorMisformattedCommandAtom(Error):
    pass

class ErrorMisformattedScalingAtom(Error):
    pass

class BadCommand(Error):
    pass

class ErrorUserCancel(Error):
    pass

class ErrorPoolOutOfRange(Error):
    pass

class ErrorBadChecksum(Error):
    pass

class ErrorCanceled(Error):
    pass