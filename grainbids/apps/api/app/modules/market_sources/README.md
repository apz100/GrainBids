# Deprecated import path

This package is a compatibility shim for older imports that referenced `app.modules.market_sources`.

Do not add new source adapters here. New integrations should import from and extend `app.platform.market_data.sources`.
