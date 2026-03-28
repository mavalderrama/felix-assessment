"""GetCorridorsUseCase — read-only corridor information for the agent."""
from __future__ import annotations

from send_money.domain.repositories import CorridorRepository


class GetCorridorsUseCase:
    def __init__(self, corridor_repository: CorridorRepository) -> None:
        self._corridors = corridor_repository

    async def get_supported_countries(self) -> list[str]:
        return await self._corridors.get_supported_countries()

    async def get_delivery_methods(self, country_code: str) -> list[str]:
        return await self._corridors.get_delivery_methods(country_code.strip().upper())
