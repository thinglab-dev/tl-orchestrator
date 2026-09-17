# Connector architecture (protected)

The transport boundary is fixed for this Story: retries live in the connector, never in the
callers, and no caller may observe a partial attempt. This document is held under
`exact_file_hash` for the whole authority, so any child batch that edits it fails closed.
