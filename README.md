# celofast

SaolaPy-backed Celonis Knowledge Model query service.

## Configuration

The package loads a local `.env` file automatically. Start by copying
`.env.example` to `.env` and filling in your tenant credentials. The external
clients read these environment variables by default:

- `CELONIS_URL`: Celonis tenant URL, for example `https://tenant.celonis.cloud`
- `OAUTH_CLIENT_ID`: OAuth client ID
- `OAUTH_CLIENT_SECRET`: OAuth client secret
- `OAUTH_SCOPES`: space-delimited OAuth scopes, for example `studio integration.data-pools`

OAuth credentials and the base URL can also be passed explicitly to
`get_celonis()` and `KnowledgeModelService` can receive an already configured
pycelonis client for testing or dependency injection.

pycelonis obtains and refreshes tokens through the tenant's standard
`/oauth2/token` endpoint and reads the OAuth variables directly.

## Query a real Knowledge Model with pycelonis

`KnowledgeModelService` uses the OAuth credentials in `.env` to find a
Knowledge Model from a single `space_id.package_id.knowledge_model_name`
string, resolve its associated Data Model, and query configured attributes:

```python
from celofast import KnowledgeModelService

KNOWLEDGE_MODEL = "SPACE_ID.PACKAGE_ID.KNOWLEDGE_MODEL_NAME"
ATTRIBUTE_COLUMNS = {
    "customer_city": '"o_celonis_Customer"."City"',
    "customer_postal_code": '"o_celonis_Customer"."PostalCode"',
    "delivery_line_number": '"o_celonis_DeliveryLine"."LineNumber"',
}

service = KnowledgeModelService(KNOWLEDGE_MODEL)
frame = service.query(ATTRIBUTE_COLUMNS, limit=10)
```

## Tests

After configuring credentials for the Celonis package indexes, install the
project and run:

```bash
uv sync
uv run pytest
```
