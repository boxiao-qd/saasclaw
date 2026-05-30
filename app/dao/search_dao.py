from app.dao.base import BaseESDAO
from app.db.elasticsearch import get_es_client
from app.config import settings
from app.schemas.search import SearchResultItem, SearchResponse
from app.schemas.common import PaginationMeta


class SearchDAO(BaseESDAO):
    async def search(self, query: str, page: int = 1, page_size: int = 20) -> SearchResponse:
        es = self._es_client
        index_name = f"{settings.es_index_prefix}-{self._employee_id}"
        from_ = (page - 1) * page_size

        body = {
            "query": {
                "bool": {
                    "must": [{"match": {"content": query}}],
                    "filter": [self._user_filter()],
                }
            },
            "from": from_,
            "size": page_size,
            "highlight": {"fields": {"content": {"fragment_size": 200}}},
        }
        result = await es.search(index=index_name, body=body)
        hits = result["hits"]["hits"]
        total = result["hits"]["total"]["value"]

        items = []
        for hit in hits:
            source = hit["_source"]
            snippet = hit.get("highlight", {}).get("content", [source.get("content", "")[:200]])[0]
            items.append(
                SearchResultItem(
                    session_id=source.get("session_id", ""),
                    session_title=source.get("session_title"),
                    snippet=snippet,
                    message_id=hit["_id"],
                    timestamp=source.get("created_at"),
                )
            )
        return SearchResponse(
            results=items,
            pagination=PaginationMeta(total=total, page=page, page_size=page_size),
        )