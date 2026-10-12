"""Compatibility entry for gap-safe exploratory PV/T baseline comparison."""

if __package__:
    from .baseline_comparison import RidgeModel, fit_ridge, main, metrics, resample_days
else:
    from baseline_comparison import RidgeModel, fit_ridge, main, metrics, resample_days

__all__ = ["RidgeModel", "fit_ridge", "metrics", "resample_days", "main"]

if __name__ == "__main__":
    main()
