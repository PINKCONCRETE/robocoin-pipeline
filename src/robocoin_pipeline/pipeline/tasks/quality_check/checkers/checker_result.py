class CheckerResult:
    def __init__(
        self,
    ) -> None:
        self.errors: str | None = None
        self.warnings: str | None = None
        self.score: float | None = None

    def set_errors(self, errors: str) -> None:
        self.errors = errors

    def set_warnings(self, warnings: str) -> None:
        self.warnings = warnings

    def set_score(self, score: float) -> None:
        self.score = score

    def to_dict(result: "CheckerResult") -> dict:
        results = {}
        if result.errors is not None:
            results["errors"] = result.errors
        if result.warnings is not None:
            results["warnings"] = result.warnings
        if result.score is not None:
            results["score"] = result.score
