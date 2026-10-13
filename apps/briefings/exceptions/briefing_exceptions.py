"""
Exceções do módulo briefings.
"""


class BriefingError(Exception):
    """Exceção base do módulo briefings."""
    pass


# =====================================================================
# TEMPLATE
# =====================================================================

class BriefingTemplateError(BriefingError):
    pass


class BriefingTemplateNotFoundError(BriefingTemplateError):
    pass


class BriefingTemplateNotDraftError(BriefingTemplateError):
    pass


class BriefingTemplateInactiveError(BriefingTemplateError):
    """Template inativo não pode originar novas execuções."""
    pass


# =====================================================================
# SECTION
# =====================================================================

class BriefingSectionError(BriefingError):
    pass


class BriefingSectionNotFoundError(BriefingSectionError):
    pass


# =====================================================================
# QUESTION
# =====================================================================

class BriefingQuestionError(BriefingError):
    pass


class BriefingQuestionNotFoundError(BriefingQuestionError):
    pass


# =====================================================================
# EXECUÇÃO
# =====================================================================

class BriefingNotFoundError(BriefingError):
    pass


class BriefingAlreadyCompletedError(BriefingError):
    pass


class BriefingClosedError(BriefingError):
    pass


class BriefingExpiredError(BriefingError):
    pass


class BriefingPausedError(BriefingError):
    pass


class InvalidQuestionSequenceError(BriefingError):
    pass


class InvalidResponseFormatError(BriefingError):
    pass


class BriefingAnswerNotFoundError(BriefingError):
    pass


class BriefingReopenError(BriefingError):
    pass


# =====================================================================
# NOTAS
# =====================================================================

class BriefingNoteError(BriefingError):
    pass


class BriefingNoteNotFoundError(BriefingNoteError):
    pass


# =====================================================================
# TRANSCRIÇÃO
# =====================================================================

class TranscriptionError(BriefingError):
    pass