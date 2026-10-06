# Configuration variables
VENV        ?= .venv
BIN         ?= $(VENV)/bin
PYTHON      ?= $(BIN)/python3
PIP         ?= $(BIN)/pip
FLAKE8      ?= $(BIN)/flake8
MYPY        ?= $(BIN)/mypy
MAP         ?= maps/01_linear_path.txt
ARGS        ?=

# Default rule: run the simulation
all: run

# Validate that MAP is provided
check_map:
ifndef MAP
	@echo "\033[31mError: MAP is required. Usage: make <command> MAP=<path>\033[0m"
	@exit 1
endif

# Create the virtual environment if it does not exist
$(VENV):
	@echo "\033[33mCreating virtual environment in $(VENV)...\033[0m"
	python3 -m venv $(VENV)

# Install project dependencies inside the virtual environment
install: $(VENV)
	@echo "\033[33mInstalling dependencies in $(VENV)...\033[0m"
	@$(PIP) install flake8 mypy

# Run the main simulation script
# For two or more ARGS: 'make run ARGS="--visual --capacity-info"'
run: check_map
	@if [ -f $(PYTHON) ]; then \
		$(PYTHON) src/main.py $(MAP) $(ARGS); \
	else \
		python3 src/main.py $(MAP) $(ARGS); \
	fi

# Run the main script in debug mode with pdb
debug:
	@if [ -f $(PYTHON) ]; then \
		$(PYTHON) -m pdb src/main.py $(MAP) $(ARGS); \
	else \
		python3 -m pdb src/main.py $(MAP) $(ARGS); \
	fi

# Run all test maps sequentially
test-all:
	@for map in maps/*.txt; do \
		echo "\033[36m\n=== $$map ===\033[0m"; \
		if [ -f $(PYTHON) ]; then \
			$(PYTHON) src/main.py "$$map" $(ARGS); \
		else \
			python3 src/main.py "$$map" $(ARGS); \
		fi \
	done

# Remove temporary files, caches, and the virtual environment
clean:
	@echo "\033[33mDeleting cache files...\033[0m"
	find . -type d -name "__pycache__" -prune -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .mypy_cache .pytest_cache
	rm -rf $(VENV)
	@echo "\033[32mEnvironment deleted. (If active in your terminal, run 'deactivate')\033[0m"

# Re-run the project from a clean state
re: clean install run

# Mandatory static analysis required by the subject (Chapter III.2)
lint:
	@echo "Testing Flake8..."
	@if [ -f $(FLAKE8) ]; then $(FLAKE8) src; else flake8 src; fi
	@echo "Testing mypy..."
	@if [ -f $(MYPY) ]; then \
		$(MYPY) src --warn-return-any --warn-unused-ignores --ignore-missing-imports --disallow-untyped-defs --check-untyped-defs; \
	else \
		mypy src --warn-return-any --warn-unused-ignores --ignore-missing-imports --disallow-untyped-defs --check-untyped-defs; \
	fi

# Strict static analysis recommended by the subject (Chapter III.2)
lint-strict:
	@echo "Testing Flake8..."
	@if [ -f $(FLAKE8) ]; then $(FLAKE8) src; else flake8 src; fi
	@echo "Testing mypy..."
	@if [ -f $(MYPY) ]; then $(MYPY) src --strict; else mypy src --strict; fi

# Phony targets that do not represent physical files
.PHONY: all install run debug test-all clean fclean re lint lint-strict
