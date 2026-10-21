# Demo tracing checks

Laminar keeps a provider singleton. Run each tracing test program in a separate
process. Initialize the provider before importing modules with `@observe`.

Run both `make verify-local` and `make verify-local-capture` after changes to
span attributes. The Oodle mirror filters content, so an SDK-only test cannot
prove that both exports retain an attribute.

Keep Cosmos ports limited to paths this demo runs. Production billing and
message routing do not exist here. Document differences instead of adding
unused production adapters.
