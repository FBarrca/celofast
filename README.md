# celofast

Reusable Celonis Knowledge Model query and export clients.

## Configuration

The package loads a local `.env` file automatically. Start by copying
`.env.example` to `.env` and filling in your tenant credentials. The external
clients read these environment variables by default:

- `CELONIS_URL`: Celonis tenant URL, for example `https://tenant.celonis.cloud`
- `CELONIS_API_TOKEN`: API token or user key
- `CELONIS_KEY_TYPE`: set to `USER_KEY` for a Bearer token; otherwise AppKey is used

Credentials and the base URL can also be passed explicitly to
`get_semantic_layer_client()` and `get_phoenix_client()`.

## Read KM data

```python
from saolapy.pql.base import PQL
from celofast import KnowledgeModel, KnowledgeModelService

km = KnowledgeModel(root_with_key="ROOT_KEY.KM_KEY")
service = KnowledgeModelService(km, draft=False)
frame = await service.export_data_frame(PQL(columns=[...]))
```

For large results, use `export_chunked()`. It starts an asynchronous Parquet
export, polls until completion, downloads the chunks sequentially, and returns
a pandas DataFrame.



Phoenix is exposed separately through `get_phoenix_client()` for augmented-
attribute value writes.

## Tests

After configuring credentials for the Celonis package indexes, install the
project and run:

```bash
uv sync
uv run pytest
```
