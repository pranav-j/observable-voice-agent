# Annotated real calls

Each file here says what the caller wanted on one real call, so recorded mode can score
it. The recordings themselves stay in `recordings/`, which is gitignored.

1. `make up` and `make dev`, then place an order from the browser. Use a made-up name
   and a fake number that starts with 90000, like 90000 31415.
2. Find the session id: the newest folder in `recordings/`.
3. `make annotate SESSION=<id>`. It prints the call and writes `<id>.yaml` here,
   starting from the agent's final order.
4. Edit that file to what you wanted, not what the agent took down.
5. `make eval MODE=recorded` scores every annotated call.
