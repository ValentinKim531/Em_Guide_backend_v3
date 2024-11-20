from typing import Optional, Union, Any, Type
from sqlalchemy.future import select
from models.models import Database, Base
from sqlalchemy import and_
from utils.logging_config import get_logger


logger = get_logger(name="crud")


class Postgres(Database):
    def __init__(self, async_session):
        self.async_session = async_session

    async def add_entity(
        self,
        entity_data: Union[dict, Base],
        model_class: type[Base],
    ) -> None:
        try:
            async with self.async_session() as session:
                if isinstance(entity_data, dict):
                    entity = model_class(**entity_data)
                else:
                    entity = entity_data
                session.add(entity)
                await session.commit()
                await session.refresh(entity)
                return entity
        except Exception as e:
            logger.error(f"Error adding entity: {e}")
            return None

    from sqlalchemy import select, and_

    async def get_entity_parameter(
        self,
        model_class: type[Base],
        filters: Optional[dict] = None,
        custom_filter: Optional[Any] = None,
    ) -> Optional[Base]:
        try:
            async with self.async_session() as session:
                query = select(model_class)

                if filters:
                    query = query.filter_by(**filters)

                if custom_filter:
                    query = query.where(
                        custom_filter
                    )  # Используем .where для добавления условия

                result = await session.execute(query)
                entity = result.scalars().first()
                return entity
        except Exception as e:
            logger.error(f"Error fetching entity parameter: {e}")
            return None

    async def get_entities_parameter(
        self, model_class: Type[Base], filters: Optional[dict] = None
    ) -> Optional[list[Base]]:
        try:
            async with self.async_session() as session:
                result = await session.execute(
                    select(model_class).filter_by(**filters)
                )
                return result.scalars().all()
        except Exception as e:
            logger.error(f"Error fetching entities parameter: {e}")
            return None

    async def get_entities(self, model_class: type) -> Optional[list]:
        try:
            async with self.async_session() as session:
                result = await session.execute(select(model_class))
                return result.scalars().all()
        except Exception as e:
            logger.error(f"Error fetching entities: {e}")
            return None

    async def update_entity_parameter(
        self,
        entity_id: Union[str, tuple],
        parameter: str,
        value: any,
        model_class: type[Base],
    ) -> None:
        try:
            async with self.async_session() as session:
                entity = await session.get(model_class, entity_id)
                if entity:
                    setattr(entity, parameter, value)
                    await session.commit()
                else:
                    logger.error(
                        f"Entity with id {entity_id} not found in {model_class.__name__}"
                    )
        except Exception as e:
            logger.error(f"Error updating entity parameter: {e}")

    async def delete_entity(
        self, entity_id: Union[str, tuple], model_class: type[Base]
    ) -> None:
        try:
            async with self.async_session() as session:
                entity = await session.get(model_class, entity_id)
                if entity:
                    await session.delete(entity)
                    await session.commit()
                else:
                    logger.error(
                        f"Entity with id {entity_id} not found in {model_class.__name__}"
                    )
        except Exception as e:
            logger.error(f"Error deleting entity: {e}")
