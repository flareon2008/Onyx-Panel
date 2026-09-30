"""Panel-only HTML helpers. No public subscription request may render admin data."""


def preview_document(source, externalize):
    """Isolated preview document for the landing-page editor.

    Network access stays disabled inside the sandbox, while inline CSS and
    JavaScript behave as they will on the published static site.
    """
    csp = ("default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
           "img-src data: blob:; font-src data:; connect-src 'none'; frame-src 'none'; "
           "base-uri 'none'; form-action 'none'")
    return '<meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="' + csp + '">' + source
