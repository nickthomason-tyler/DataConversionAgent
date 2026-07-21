"""Typed errors with stable process exit codes."""


class ConversionAgentError(Exception):
    exit_code = 1


class SettingsError(ConversionAgentError):
    exit_code = 2


class ProjectError(ConversionAgentError):
    exit_code = 3


class ProjectValidationError(ProjectError):
    pass


class WorkbookError(ConversionAgentError):
    exit_code = 4


class BackendError(ConversionAgentError):
    exit_code = 5


class OutputError(ConversionAgentError):
    exit_code = 6
