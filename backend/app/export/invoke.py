"""Call a FastAPI endpoint function directly, outside a request.

Export endpoints use this to run the *page's own* JSON endpoint (same
cache key, same Tally fetch, same post-processing), so a PDF/Excel export
can never disagree with what the screen shows.
"""

import inspect


async def invoke_endpoint(endpoint, **given):
    kwargs = {}
    for name, param in inspect.signature(endpoint).parameters.items():
        if name in given:
            kwargs[name] = given[name]
            continue
        default = param.default
        if default is inspect.Parameter.empty:
            continue
        value = getattr(default, "default", default)
        if value is Ellipsis or type(value).__name__ == "PydanticUndefinedType":
            value = None
        kwargs[name] = value
    return await endpoint(**kwargs)
