# Quick Review Checklist

Use this checklist for efficient code reviews.

## Critical (Must Fix)
- [ ] Security vulnerabilities
- [ ] Data loss risks
- [ ] Crashes or unhandled exceptions
- [ ] Breaking changes to public APIs
- [ ] Performance issues under load

## Important (Should Fix)
- [ ] Missing error handling
- [ ] Missing input validation
- [ ] Missing or inadequate tests
- [ ] Code that's hard to understand
- [ ] Violations of coding standards

## Minor (Nice to Have)
- [ ] Style improvements
- [ ] Additional documentation
- [ ] Code organization
- [ ] Performance micro-optimizations

## Questions to Ask
1. Would I understand this code in 6 months?
2. Can I easily test this code?
3. Does this handle failure gracefully?
4. Is this the simplest solution?
