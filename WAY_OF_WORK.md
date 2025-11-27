# Development Methodology

**Version:** 3.0.0  
**Last Updated:** 2025-11-21

---

## Philosophy

This document defines our **standardized** approach to software development. It enforces industry best practices while maintaining flexibility for project-specific needs.

### Core Principles

1. **SOLID Principles**
   - Single Responsibility: Each class/module has one reason to change
   - Open/Closed: Open for extension, closed for modification
   - Liskov Substitution: Subtypes must be substitutable for base types
   - Interface Segregation: Many specific interfaces over one general
   - Dependency Inversion: Depend on abstractions, not concretions

2. **DRY (Don't Repeat Yourself)**
   - Abstract common functionality
   - Use delegation to specialized components
   - Share code through libraries/modules

3. **KISS (Keep It Simple, Stupid)**
   - Prefer simple solutions over clever ones
   - Write code humans can understand
   - Avoid premature optimization

4. **YAGNI (You Aren't Gonna Need It)**
   - Don't build features you don't need yet
   - Focus on current requirements
   - Extend when necessary, not preemptively

5. **Separation of Concerns**
   - Clear boundaries between components
   - Each layer handles its responsibility
   - Minimal coupling, high cohesion

---

## Development Workflow

### Phase 1: Documentation First
**Before writing any code:**
1. Document the problem being solved
2. Define success criteria
3. Outline approach and alternatives
4. Track research in `docs/research/`

### Phase 2: Test-Driven Development
**Always write tests before production code:**
1. Write failing tests that define behavior
2. Write minimum code to make tests pass
3. Refactor while keeping tests green
4. Document test strategy

### Phase 3: Implementation
**Following the test framework:**
1. Implement features incrementally
2. Follow established patterns
3. Keep functions small and focused
4. Document complex logic

### Phase 4: Review & Refactor
**Continuous improvement:**
1. Review code for SOLID violations
2. Check for duplication (DRY)
3. Simplify where possible (KISS)
4. Remove unused code (YAGNI)

---

## Project Structure

### Universal Structure
```
project-root/
├── src/                    # Production code
│   ├── core/              # Core business logic
│   ├── api/               # API/interface layer
│   └── utils/             # Shared utilities
├── tests/                 # Test code
│   ├── unit/             # Unit tests
│   ├── integration/      # Integration tests
│   └── fixtures/         # Test fixtures
├── docs/                  # Documentation
│   ├── research/         # Research notes
│   ├── architecture/     # Architecture decisions
│   └── api/              # API documentation
├── WAY_OF_WORK.md        # This file
├── CLAUDE.md             # Project context for Claude
└── README.md             # Project overview
```

---

## Code Quality Standards

### All Languages
- **No magic numbers**: Use named constants
- **Meaningful names**: Variables/functions describe their purpose
- **Single purpose**: Functions do one thing well
- **Error handling**: All errors handled explicitly
- **Documentation**: Complex logic explained in comments

### Python Specific
- Use type hints for function signatures
- Follow PEP 8 style guide
- Use context managers (RAII pattern)
- Prefer list comprehensions over loops (when clear)
- Use dataclasses/pydantic for data structures

### JavaScript/TypeScript Specific
- Use strict mode
- Prefer const over let, never var
- Use async/await over raw promises
- TypeScript: Enable strict mode
- Use interfaces for contracts

---

## Testing Standards

### Coverage Requirements
- **Minimum**: 80% code coverage
- **Target**: 90% code coverage
- **Critical paths**: 100% coverage

### Test Types
1. **Unit Tests**: Test individual functions/classes
2. **Integration Tests**: Test component interactions
3. **E2E Tests**: Test complete workflows

### Test Organization
- Mirror source code structure in tests/
- One test file per source file
- Group related tests with descriptive names
- Use fixtures for common setup

---

## Documentation Requirements

### Required Documents
1. **README.md**: Project overview, setup, usage
2. **WAY_OF_WORK.md**: This methodology (universal)
3. **CLAUDE.md**: Project-specific context for Claude
4. **API docs**: If project exposes APIs

### Research Tracking
- All research goes in `docs/research/`
- One file per investigation/feature
- Include date, question, findings, decision

---

## Version Control

### Commit Messages
Format: `<type>(<scope>): <description>`

Types:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `test`: Test changes
- `refactor`: Code refactoring
- `style`: Formatting changes
- `chore`: Maintenance tasks

Example: `feat(auth): add JWT token validation`

### Branch Strategy
- `main`: Production-ready code
- `develop`: Integration branch
- `feature/*`: Feature branches
- `fix/*`: Bug fix branches

---

## Remote Server Debugging Workflow

When working with code deployed on remote servers, follow this workflow to maintain code quality and version control:

### Investigation Phase (Remote)
**Purpose**: Diagnose issues on production/staging servers

1. **SSH to Remote Server**: Connect and investigate the issue
   ```bash
   ssh user@remote-server
   ```

2. **Reproduce the Error**: Trigger the issue and capture error messages
   - Check application logs
   - Run failing endpoints/commands
   - Note exact error messages and stack traces

3. **Investigate Root Cause**: Use remote debugging tools
   - Check service logs: `journalctl -u service-name`
   - Test components manually
   - Verify environment configuration
   - Check file permissions and paths

### Fix Phase (Local)
**Purpose**: Implement fixes in a controlled, tested environment

4. **Return to Local Development**: Switch to local repository
   ```bash
   cd /path/to/local/project
   ```

5. **Reproduce Locally** (if possible): Verify you can reproduce the issue
   - Use same test data
   - Match remote environment conditions

6. **Write/Update Tests**: Add tests that expose the bug
   - Write failing test first (TDD)
   - Ensure test catches the exact issue

7. **Implement Fix**: Make code changes locally
   - Fix the root cause identified remotely
   - Follow existing code patterns
   - Keep changes minimal and focused

8. **Verify Tests Pass**: Run full test suite
   ```bash
   pytest
   ```

9. **Commit and Push**: Version control the fix
   ```bash
   git add <changed-files>
   git commit -m "fix: description of bug fix"
   git push origin master
   ```

### Deployment Phase (Remote)
**Purpose**: Apply tested fixes to production

10. **Pull on Remote Server**: Update remote code
    ```bash
    ssh user@remote-server
    cd /path/to/project
    git pull origin master
    ```

11. **Restart Services**: Apply changes
    ```bash
    sudo systemctl restart service-name
    ```

12. **Verify Fix**: Confirm issue is resolved
    - Test the previously failing scenario
    - Check logs for errors
    - Monitor for a period

### Key Principles

**✅ DO:**
- Investigate issues on remote servers to understand context
- Always fix code in local repository with tests
- Commit all fixes to version control
- Pull changes to remote servers via git

**❌ DON'T:**
- Edit code directly on production/remote servers
- Make "quick fixes" that bypass version control
- Skip writing tests for bug fixes
- Deploy untested changes

### Benefits of This Workflow
- ✅ All changes tracked in version control
- ✅ Changes are tested before deployment
- ✅ Easy to roll back if needed
- ✅ Team visibility into all changes
- ✅ Maintains code quality standards
- ✅ Enables proper code review

---

## Skill Coordination

This methodology works with specialized Claude skills:

### Delegation Strategy
1. **Code Review**: Delegate to `fastapi-review` skill (security, quality)
2. **Testing**: Delegate to `test-driven-development` skill (TDD workflows)
3. **Debugging**: Delegate to `systematic-debugging` skill (investigation)
4. **Standards**: This skill coordinates and tracks compliance

### Benefits of Delegation
- ✅ Specialized expertise for each domain
- ✅ Higher quality results
- ✅ No duplication of effort
- ✅ Coordinated workflow

---

## Continuous Improvement

### Regular Reviews
- Monthly compliance audits
- Quarterly methodology reviews
- Annual retrospectives

### Metrics Tracking
- Code coverage trends
- Compliance scores
- Issue resolution time
- Technical debt tracking

### Skill Updates
- Check for skill updates monthly
- Migrate metadata when updating
- Review changelog before updating
- Test updates in non-critical projects first

---

## Questions & Support

For questions about this methodology:
1. Review this document thoroughly
2. Check project-specific CLAUDE.md
3. Consult with team/Claude
4. Propose improvements via issues/PRs

Remember: **Standards enable consistency, delegation enables excellence!** 🎯
