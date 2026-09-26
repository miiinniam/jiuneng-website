from fastapi import APIRouter, HTTPException, Query

from app.services.geocoder import GeocoderError, search_address

router = APIRouter()


@router.get("/geocode")
async def geocode(q: str = Query(..., min_length=1), limit: int = Query(5, ge=1, le=10)) -> list[dict]:
    try:
        results = await search_address(q, limit=limit)
    except GeocoderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return [{"lat": r.lat, "lng": r.lng, "display_name": r.display_name} for r in results]
