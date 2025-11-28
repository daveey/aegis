"""Prompt template management for Aegis agents.

This module provides functionality to load, render, and manage prompt templates
for different agent types and task scenarios.
"""

from datetime import datetime
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from aegis.database.models import PromptTemplate
from aegis.database.session import get_db_session

logger = structlog.get_logger(__name__)


class PromptRenderer:
    """Renders prompt templates with dynamic variables."""

    @staticmethod
    def render(template: str, variables: dict[str, Any]) -> str:
        """Render a template string with provided variables.

        Uses simple string formatting with named placeholders.

        Args:
            template: Template string with {variable_name} placeholders
            variables: Dictionary of variable names to values

        Returns:
            Rendered template string

        Example:
            >>> template = "Hello {name}, you have {count} tasks."
            >>> variables = {"name": "Alice", "count": 5}
            >>> PromptRenderer.render(template, variables)
            'Hello Alice, you have 5 tasks.'
        """
        try:
            return template.format(**variables)
        except KeyError as e:
            logger.warning("missing_template_variable", variable=str(e), template_preview=template[:100])
            # Return template with missing variables as-is rather than failing
            return template
        except Exception as e:
            logger.error("template_render_error", error=str(e), template_preview=template[:100])
            return template


class PromptTemplateLoader:
    """Loads prompt templates from the database."""

    @staticmethod
    def get_active_template(
        agent_type: str, template_name: str, session: Session | None = None
    ) -> PromptTemplate | None:
        """Get the active template for an agent type and name.

        Args:
            agent_type: Type of agent (e.g., "simple_executor", "code_specialist")
            template_name: Name of the template (e.g., "system", "code_task", "research_task")
            session: Optional database session (will create if not provided)

        Returns:
            PromptTemplate object or None if not found
        """
        if session is not None:
            # Use provided session
            stmt = (
                select(PromptTemplate)
                .where(
                    PromptTemplate.agent_type == agent_type,
                    PromptTemplate.name == template_name,
                    PromptTemplate.active == True,  # noqa: E712
                )
                .order_by(PromptTemplate.version.desc())
            )

            result = session.execute(stmt)
            template = result.scalar_one_or_none()

            if template:
                logger.info(
                    "template_loaded",
                    agent_type=agent_type,
                    template_name=template_name,
                    version=template.version,
                )
            else:
                logger.warning(
                    "template_not_found",
                    agent_type=agent_type,
                    template_name=template_name,
                )

            return template
        else:
            # Create own session
            with get_db_session() as session:
                stmt = (
                    select(PromptTemplate)
                    .where(
                        PromptTemplate.agent_type == agent_type,
                        PromptTemplate.name == template_name,
                        PromptTemplate.active == True,  # noqa: E712
                    )
                    .order_by(PromptTemplate.version.desc())
                )

                result = session.execute(stmt)
                template = result.scalar_one_or_none()

                if template:
                    # Eagerly access attributes before session closes to avoid DetachedInstanceError
                    _ = (
                        template.name,
                        template.version,
                        template.system_prompt,
                        template.user_prompt_template,
                        template.description,
                        template.variables,
                        template.tags,
                        template.usage_count,
                    )

                    logger.info(
                        "template_loaded",
                        agent_type=agent_type,
                        template_name=template_name,
                        version=template.version,
                    )

                    # Expunge from session so it can be used after session closes
                    session.expunge(template)
                else:
                    logger.warning(
                        "template_not_found",
                        agent_type=agent_type,
                        template_name=template_name,
                    )

                return template

    @staticmethod
    def get_all_templates_for_agent(
        agent_type: str, session: Session | None = None
    ) -> dict[str, PromptTemplate]:
        """Get all active templates for an agent type.

        Args:
            agent_type: Type of agent
            session: Optional database session

        Returns:
            Dictionary mapping template names to PromptTemplate objects
        """
        if session is not None:
            stmt = (
                select(PromptTemplate)
                .where(
                    PromptTemplate.agent_type == agent_type,
                    PromptTemplate.active == True,  # noqa: E712
                )
                .order_by(PromptTemplate.name, PromptTemplate.version.desc())
            )

            result = session.execute(stmt)
            all_templates = result.scalars().all()

            # Keep only the highest version for each template name
            templates_by_name: dict[str, PromptTemplate] = {}
            for template in all_templates:
                if template.name not in templates_by_name:
                    templates_by_name[template.name] = template

            logger.info(
                "templates_loaded",
                agent_type=agent_type,
                count=len(templates_by_name),
                templates=list(templates_by_name.keys()),
            )

            return templates_by_name
        else:
            with get_db_session() as session:
                stmt = (
                    select(PromptTemplate)
                    .where(
                        PromptTemplate.agent_type == agent_type,
                        PromptTemplate.active == True,  # noqa: E712
                    )
                    .order_by(PromptTemplate.name, PromptTemplate.version.desc())
                )

                result = session.execute(stmt)
                all_templates = result.scalars().all()

                # Keep only the highest version for each template name
                templates_by_name: dict[str, PromptTemplate] = {}
                for template in all_templates:
                    if template.name not in templates_by_name:
                        # Eagerly access attributes before session closes
                        _ = (
                            template.name,
                            template.version,
                            template.system_prompt,
                            template.user_prompt_template,
                            template.description,
                            template.variables,
                            template.tags,
                            template.usage_count,
                        )
                        session.expunge(template)
                        templates_by_name[template.name] = template

                logger.info(
                    "templates_loaded",
                    agent_type=agent_type,
                    count=len(templates_by_name),
                    templates=list(templates_by_name.keys()),
                )

                return templates_by_name


class PromptBuilder:
    """High-level interface for building complete prompts."""

    def __init__(self, agent_type: str):
        """Initialize the prompt builder.

        Args:
            agent_type: Type of agent to build prompts for
        """
        self.agent_type = agent_type
        self.renderer = PromptRenderer()
        self.loader = PromptTemplateLoader()

    def build_prompt(
        self,
        template_name: str,
        variables: dict[str, Any],
        session: Session | None = None,
    ) -> tuple[str, str] | None:
        """Build a complete prompt with system and user components.

        Args:
            template_name: Name of the template to use
            variables: Variables to render in the template
            session: Optional database session

        Returns:
            Tuple of (system_prompt, user_prompt) or None if template not found
        """
        template = self.loader.get_active_template(
            self.agent_type, template_name, session
        )

        if not template:
            logger.error(
                "prompt_build_failed",
                agent_type=self.agent_type,
                template_name=template_name,
                reason="template_not_found",
            )
            return None

        # Add standard variables
        enhanced_variables = {
            "current_date": datetime.now().strftime("%Y-%m-%d"),
            "current_datetime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            **variables,
        }

        system_prompt = self.renderer.render(template.system_prompt, enhanced_variables)
        user_prompt = self.renderer.render(template.user_prompt_template, enhanced_variables)

        logger.info(
            "prompt_built",
            agent_type=self.agent_type,
            template_name=template_name,
            template_version=template.version,
            system_prompt_length=len(system_prompt),
            user_prompt_length=len(user_prompt),
        )

        return system_prompt, user_prompt

    def increment_usage(
        self, template_name: str, session: Session | None = None
    ) -> None:
        """Increment the usage count for a template.

        Args:
            template_name: Name of the template
            session: Optional database session
        """
        if session is not None:
            template = self.loader.get_active_template(
                self.agent_type, template_name, session
            )

            if template:
                template.usage_count += 1
                # Don't commit here - let the caller manage the transaction

                logger.debug(
                    "template_usage_incremented",
                    agent_type=self.agent_type,
                    template_name=template_name,
                    new_count=template.usage_count,
                )
        else:
            with get_db_session() as session:
                template = self.loader.get_active_template(
                    self.agent_type, template_name, session
                )

                if template:
                    template.usage_count += 1
                    # Session context manager will commit

                    logger.debug(
                        "template_usage_incremented",
                        agent_type=self.agent_type,
                        template_name=template_name,
                        new_count=template.usage_count,
                    )
