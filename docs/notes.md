# Build notes

Problems I ran into while building this, roughly in the order they came up, and what I did about each. Design decisions with real alternatives are in [adr/](adr/). This file is the messier side of it.

## CI broke on its first run because GitHub's runners have nvm

The Makefile switches to the Node version in `.nvmrc` by sourcing nvm. Make runs every recipe in a plain shell that never reads `~/.zshrc`, so without that step it picks up whatever Node is the global default. I assumed CI had no nvm and the step would be skipped there. It does have nvm. But `setup-node` installs Node into its own tool cache, not into nvm, so `nvm use` failed with "version not installed".

The fix was to ask a better question. If the `node` on PATH already matches `.nvmrc`, do nothing, and only use nvm when it doesn't. I tested both paths locally, including one with a fake nvm that fails if it's ever called. actionlint had passed the workflow file, and it was right to. Only a real run catches a wrong assumption about the machine it runs on.

## Fuzzy search matched "latte" inside "sushi platter"

I started with rapidfuzz's `WRatio`, the usual default. While writing tests for things that aren't on the menu, I tried "sushi platter", and it came back as a strong match for Cafe Latte. `WRatio` includes a partial match that works on characters, and "platter" contains "latte". For a voice agent that's a bad failure mode, because the agent ends up saying "yes, we have that".

I replaced it with my own scorer: the better of a whole-string ratio (good for transcription typos like "pesaratu") and a word-set overlap scaled down slightly (good for partial names and word order). Neither one looks inside words. "sushi platter" and "chained" stay in the tests as regression cases. The tests also require a clear gap between real matches and things that aren't on the menu, so the agent gets a match label it can rely on instead of a raw score.

## The model can't place an order unless code allows it

Order state lives in code, and the LLM only changes it through tools. Every change bumps a `mutation_seq`. `get_readback` records that number, and `confirm_order` refuses unless the two match. So "any change after the read-back needs a new read-back" is something the model can't skip, however it phrases things. To check that the tests guard this, I deleted the check on purpose, and the tests failed.

Prices work the same way. Orders store no prices at all, only what was chosen. Every rupee is computed from the menu when it's needed, in integer paise, so a price can't go stale, and there's nowhere for a number made up by the model to end up.

## A fixed caller script falls out of step

For my first end-to-end test I piped a list of caller lines into the chat. The agent asked for the name one turn earlier than I'd guessed, so every line after that answered the wrong question. My "yes" ended up confirming the phone number instead of the read-back, and the order ended up abandoned. The agent did nothing wrong. This is why the eval harness uses an LLM to play the caller, so it reacts to what the agent actually says, with scripted lines only for specific moments like interrupting the read-back.

## The scripted interruption fought the caller's own goal

In the barge-in scenario, the caller's goal says a large coffee, and the scripted interruption changes it to medium. The LLM caller would hear the corrected read-back, compare it with its goal, and "fix" it back to large, which ruins the test. I added a rule to the caller prompt: what you said earlier in the call wins over the goal.

## Green CI can hide skipped tests

The Postgres integration tests skip themselves when there's no database. A skipped test still gives a green build. After adding a Postgres service to CI, I didn't trust the green tick alone. I checked the log to make sure those tests had run and passed.

## Making sure the tests can actually fail

A few times I broke the code on purpose and checked that something went red:

- deleted the read-back check
- made the agent loop never save the order
- dropped modifier prices from the total
- swapped the optimal line matching in the scorer for a greedy one

A test suite that has never failed hasn't proven much.

## Scoring partial credit needs optimal matching

To score how close a wrong order was, expected lines have to be paired with actual lines. Pairing greedily, where each expected line grabs its best match in turn, can undercount. There's a test built so that greedy gets half the fields while the best pairing gets three quarters. I solved it with a small dynamic program over which actual lines are already used. It's exact and fast enough for the few lines an order has.

## I don't tune scenarios until the agent passes

Before committing new scenarios, I run each one once on the real model. The point is to catch mistakes in the scenario itself, like an ambiguous goal or a wrong expected order. I only change a scenario if the scenario is wrong. Rewording it until the agent passes would quietly bias the baseline toward success.

## A scenario passed without testing anything

One barge-in scenario had the caller interrupt the read-back with "drop the samosa", and expected an order without it. It passed. When I read the transcript, the samosa had never been added in the first place. That was the plural bug below. So there was nothing to remove, and the final order matched anyway. The scenario couldn't tell "removed" from "never added".

I changed the item being dropped to a brownie, which doesn't hit the search problem, and checked that the agent now calls `remove_item` and gives a fresh read-back. The plural bug gets its own scenario instead of being caught by accident. Since then I check each new scenario's transcript to confirm the behavior it's named after actually happened, not just that it passed.

## The agent confirmed before the caller answered

While checking new scenarios, I read the transcripts even for runs that passed. In one, the agent read the order back, asked "Is that correct?", and called `confirm_order` in the same turn, before the caller could say anything. The order happened to be right, so the run scored as a success.

That's two problems. The agent skipped the rule about waiting for a yes, and my scoring couldn't see it. The code rule only checks that a read-back happened after the last change, not that the caller replied to it.

The plan is to measure first, and the measuring part is done. Every report now lists runs where the agent confirmed in the same turn as the read-back, under "Rule violations". I kept it separate from task success on purpose. If I changed what task success means halfway through, the before and after reports couldn't be compared.

Next I'll record the baseline, then add a code guard and re-run. The guard: `confirm_order` only works if the caller has spoken since the read-back. Code can't decide whether the reply was actually a yes, which stays with the model, but it can make sure the caller got the chance to answer.

## Plurals and filler words weaken search

"one plate of veg samosas" didn't find Veg Samosa on the first search. The agent needed a second one. Plurals and extra words pull the score down.

A later run was worse. The agent searched for "one plate of veg samosas", got only weak matches, and told the caller that veg samosas "aren't available on the menu". They are on the menu, and in stock. So this bug can lose a sale, not just cost an extra search. The fix I have in mind is to singularize query words before scoring. Same plan as above: baseline first, then fix and compare. A dedicated scenario will catch it on purpose.

## The agent sometimes skips end_call

After saying goodbye, the agent doesn't always call `end_call`. In text mode it doesn't matter, but in a voice call the line would stay open. Every eval run records how the call ended, so I can see how often this happens before touching the prompt.
