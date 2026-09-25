PYTHON ?= python3
CODEX_HOME ?= $(HOME)/.codex
VENV_PYTHON := .venv/bin/python
SKILL_VALIDATOR ?= $(CODEX_HOME)/skills/.system/skill-creator/scripts/quick_validate.py

.PHONY: validate

validate: $(VENV_PYTHON)
	@$(VENV_PYTHON) -c 'import yaml' 2>/dev/null || $(VENV_PYTHON) -m pip install PyYAML
	@$(VENV_PYTHON) "$(SKILL_VALIDATOR)" .

$(VENV_PYTHON):
	$(PYTHON) -m venv .venv
