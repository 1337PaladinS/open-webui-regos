.PHONY: install interactive dry-run clean help

install:
	@./install.sh

interactive:
	@./install.sh --interactive

dry-run:
	@./install.sh --dry-run --verbose

step-%:
	@./install.sh --step $(subst step-,,$@)

verify:
	@./install.sh --step 08

clean:
	@rm -f regos-install.log

help:
	@echo "RegOS Installer"
	@echo ""
	@echo "Targets:"
	@echo "  make install       Run full installation"
	@echo "  make interactive   Run with prompts"
	@echo "  make dry-run       Preview without changes"
	@echo "  make step-05       Run a single step (e.g., step-05)"
	@echo "  make verify        Run verification only"
	@echo "  make clean         Remove log files"
	@echo "  make help          Show this help"
