"""
Exceções do módulo clients.
"""


class ClientError(Exception):
    """Base do módulo clients."""
    pass


# ---- Client ----

class ClientNotFoundError(ClientError):
    pass


class ClientDuplicateEmailError(ClientError):
    pass


class ClientPublicCodeError(ClientError):
    pass


# ---- Contact ----

class ContactNotFoundError(ClientError):
    pass


# ---- Note ----

class NoteNotFoundError(ClientError):
    pass


# ---- Portal ----

class PortalAccessError(ClientError):
    pass


class PortalEmailMissingError(PortalAccessError):
    """Cliente não possui email válido para receber acesso."""
    pass


class PortalSessionError(PortalAccessError):
    pass


class PortalSessionExpiredError(PortalAccessError):
    pass