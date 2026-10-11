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

A later run was worse. The agent searched for "one plate of veg samosas", got only weak matches, and told the caller that veg samosas "aren't available on the menu". They are on the menu, and in stock. So this bug can lose a sale, not just cost an extra search.

When I probed the search directly, it turned out to be mostly the filler words, not the plural. "veg samosas" scores as a strong match, and "two plates of veg samosas" falls below the weak line. So it depends on how the model phrases its query. When it trims the caller's words down to the item name, everything works. When it passes them straight through, it fails. That makes the bug intermittent, which is exactly the kind of thing several runs per scenario are for. The fix should strip quantities and words like "plate of" and "some" before scoring, and maybe singularize too. Same plan as above: baseline first, then fix and compare.

## The agent asked a question, then answered it itself and hung up

In one run the caller asked for "a cold brew coffee", which matches Cold Brew and Cold Coffee equally. The agent did the right thing at first and asked which one. Then, in the same turn, with no reply from the caller, it added the cold brew on its own and called `end_call` with the reason "caller stopped responding". It invented the silence.

Part of the cause is my loop. When the model returns text and tool calls together, the loop keeps calling it so it can finish its tool work, which is what you want for "let me check that" plus a search. Here the model kept going past its own question and treated the extra rounds as time passing. It doesn't happen every time; the re-run was fine.

The next batch of scenarios showed it isn't a one-off. It's the most common way the agent fails. In three runs it asked for the phone number and, in the same breath, called `set_customer` with an answer it made up: an empty string, a single space, and "0000000000". One run then ended the call because the caller had "stopped responding". Another tried the blank number three times within that one turn, which tripped my prompt rule to transfer after three failed attempts at the same step. So it escalated over failures it had produced itself. And in the scenario where the caller asks for a person, it transferred on the first request instead of the second, right after asking "would you like to place an order?".

I'm leaving the fix until after the baseline. The likely shape is a code rule in the loop: if the model's words in a round end with a question to the caller, run that round's tool calls but don't call the model again, and end the turn so the caller can answer. It's a heuristic, but a narrow one, and easy to test. The "three failed attempts" count should also only count attempts across caller turns, not retries inside one turn.

## A made-up phone number passed validation

The phone check strips non-digits, handles a +91 or leading 0, and requires ten digits. "0000000000" is ten digits, so when the agent invented it as a placeholder, it was saved as the customer's number. Indian numbers don't start with 0 once the prefix is gone, so the check should reject a leading zero. It's a small rule, but without it, an order could be confirmed with a phone number nobody can call.

## The read-back drops pack sizes

The menu has "Veg Samosa (2 pcs)". I decided the read-back shouldn't speak the bracket, so it says "Two Veg Samosa". That sounds like two samosas, when it's really two plates of two. In one run the simulated caller kept saying "no, two plates" at the read-back, until the agent asked whether two pieces per plate was what they meant. A real person could get stuck in the same place. The read-back should probably keep the pack size, something like "two Veg Samosa, two pieces each". That decision cost something I hadn't thought about.

## The text-mode baseline

With all 31 scenarios written, I ran each one three times: 93 calls, with `gpt-6-luna` playing both the agent and the caller, on prompt v1. The report is [reports/20261011-074743-text/summary.md](../reports/20261011-074743-text/summary.md). All numbers here come from it or from its `summary.json`.

- Task success was 67.7% (63 of 93 runs), and 11 of 31 scenarios passed all three runs.
- Order exact match was 72.2% of the scored runs, with a mean field accuracy of 0.90.
- The agent transferred 12 calls when 3 transfers were expected.
- 4 runs confirmed in the same turn as the read-back, before the caller could answer.

Reading the failures, most of them come from one behavior: the agent asks something and then carries on as if it had heard an answer. In 15 of the 30 failed runs the customer's details were never set. 9 failed runs ended in a transfer nobody asked for, often after the agent had submitted blank phone numbers on the caller's behalf.

The worst cases are 3 runs where the agent made up a phone number, 98765 43210. Nobody in the scenarios has that number. In one of them, the order was confirmed with it. That run is also one of the 4 flagged for confirming before the caller replied, so the metric earned its place on its first real run.

The understanding side held up well. Hinglish, misheard dish names, injection attempts, price questions and swapping an item mid-answer all passed every run. The problems are about when the agent stops talking, not what it understands.

The order I want to fix things in, re-running after each so every change gets its own before and after:

1. End the turn when the agent asks the caller a question, and only count failed attempts across caller turns.
2. Reject phone numbers with a leading zero.
3. Strip quantities and filler from search queries.
4. Keep the pack size in the read-back.
5. A code guard so `confirm_order` needs the caller to have spoken since the read-back.

One caveat on the numbers: a couple of the failures were the simulated caller hanging up at the read-back, not the agent. More on that below.

## Fix 1: a question to the caller ends the turn

The main failure in the baseline was the agent asking something and then carrying on as if it had heard an answer. Looking at the failing turns, the model was returning words and tool calls in the same reply, like "What's your phone number?" plus a `set_customer` with a blank phone. My loop then called the model again to finish its tool work, and from there it spiralled: retries, invented silence, transfers.

The fix is a rule in the loop. If the model's words in a round contain a question, the turn ends after that round, and the caller gets to answer. Order changes in that same reply still run, because "I've added the dosa. Anything else?" is a normal thing to say. But the read-back, confirming, ending the call and transferring are held back and get a "waiting for the caller" result instead. The API needs a result for every tool call, so the model also learns why they didn't run. I didn't touch the prompt, so the before and after differ by this one change.

Same 31 scenarios, three runs each. Report: [reports/20261011-080849-text/summary.md](../reports/20261011-080849-text/summary.md), compared with the baseline:

- Task success went from 67.7% to 93.5% (87 of 93 runs).
- 27 of 31 scenarios now pass all three runs, up from 11.
- Transfers went from 12 to 4, with 3 expected.
- Failed runs where the customer's details were never set went from 15 to 0.
- The invented phone number didn't appear at all.

One number went the "wrong" way. Premature confirm attempts went from 4 to 10. The metric counts attempts on purpose, so I checked the transcripts. Every one of them was held back by the new rule, and none went through. My guess is that more runs now reach the read-back at all, since fewer derail early, which gives the model more chances to try. Either way, the rule held every time.

The six failures left are mostly about my test setup, not the agent:

- **A fragile scenario.** In the drop-the-brownie scenario, the agent read the order back before the caller had ordered the brownie, so the scripted "drop the brownie" fired too early. The agent handled it fine ("there isn't a brownie on your order"), then the caller added the brownie afterwards. The scenario assumed the item would be there. The agent also read back before the caller said they were done, which is its own small problem.
- **The caller said yes to wrong read-backs twice.** The agent had lost a quantity change in one run and a drink in another, so the agent is to blame for those orders. But a real person would have caught them at the read-back.
- **The caller misread its own number.** The agent read back "90000 00013" correctly, and the caller insisted the right number was 9000000013, which is the same thing. The agent transferred after that one mismatch, which is too quick.
- **A harness bug.** The caller's last message was "Yes, that's correct. Goodbye." together with its end-of-call marker. My runner stopped at the marker and never passed the "yes" to the agent, so the order stayed unconfirmed. I'd suspected this earlier and found no case of it then. This time it happened.

Before the next agent fix I want the harness to be fair. The caller's last words should always reach the agent, and an early hang-up by the caller should get its own label. Otherwise I'd be measuring the agent against my own bugs.

## Fixing the harness, and a new reference run

Before fixing anything else in the agent, I fixed the two measurement problems from the last run. The caller's last words now always reach the agent while the order is still open, so "yes, that's correct, goodbye" can still confirm it. A caller who leaves mid-order now gets its own end reason, `caller_hung_up_early`, so the report shows it instead of quietly counting it as the agent's failure. I also changed the drop-the-brownie scenario so the caller orders everything in the first sentence, which means the scripted interruption can't fire before the brownie exists.

Then I re-ran everything as the new reference point. Report: [reports/20261011-083619-text/summary.md](../reports/20261011-083619-text/summary.md). Task success was 94.6% (88 of 93), against 93.5% (87 of 93) after fix 1, and 27 of 31 scenarios passed all three runs, the same as before.

I don't read anything into that one extra run. With 93 runs, a single run is within the normal variation from one suite run to the next. What did change is which runs failed. The harness failure and the fragile scenario are gone, and a few different scenarios failed this time. The new label also showed up: 2 of the 5 failures were the simulated caller hanging up mid-order.

The other three are real agent problems, and all of them point at code rather than the prompt:

- **Filler words in search** again. A run lost the veg samosa.
- **It couldn't swap an item.** To turn a latte into a cappuccino, it called `update_item`, which can only change quantity, size and modifiers, not the item itself. The call failed, and the agent told the caller it couldn't replace it, instead of removing the latte and adding a cappuccino. The error message should tell the model to do exactly that.
- **It dropped a zero.** The caller said "nine zero zero zero zero, zero zero zero two three", and the model turned it into a nine-digit number. That failed validation twice and ended in a transfer. Counting repeated words is something language models are bad at, and it's easy to do in code. So the phone parser should understand spoken digits, and the model can pass the caller's words through as they are.

So the list of agent fixes is now: filler words in search, spoken digits in phone numbers, rejecting a leading zero, a clearer error for swapping items, pack sizes in the read-back, and the code guard on confirming. Each one gets its own run against this reference.

## Fix 2: search ignores quantities and filler words

By now only about five runs in 93 were failing, and a full suite run varies by a few runs from one go to the next. A small fix would disappear into that noise. So for this one I changed how I measure. Unit tests prove the deterministic part. Then I run only the affected scenarios, ten times each, once before the change and once after.

The change: before scoring, search also builds a cleaned copy of the query. It drops quantities ("two", "a", "2") and filler ("plate of", "some", "please"), and turns a plural into its singular when the singular is a menu word ("samosas" becomes "samosa"). It scores both the original and the cleaned query and keeps the better result, so the cleaning can only help. Only whole words are dropped, so "sushi platter" stays a weak match. While probing, I found a case I hadn't known about: "some masala dosas please" used to pick the Mysore Masala Dosa. Now it finds the right one.

On the two samosa scenarios, ten runs each: before was 10 of 20 ([report](../reports/20261011-085500-text/summary.md)), after was 15 of 20 ([report](../reports/20261011-085827-text/summary.md)). The details-up-front scenario went from 4 to 8 of 10, and the plural one from 6 to 7.

I wouldn't lean too hard on those numbers. Twenty runs a side is small, and part of that jump could be chance. The better evidence is what's left. None of the remaining failures is a search miss anymore: queries like "plate of veg samosas" now find the item every time. Most of the leftover failures come from plates versus pieces. The agent recorded 2 and 4 where 1 and 2 plates were meant, and the simulated caller hung up three times after hearing "Two Veg Samosa" read back. So fixing the pack size in the read-back moves up the list.

## The simulated caller can be the thing that fails

Two failures in one batch came from my side of the test, not the agent. In one, I'd told the caller to say "two plates of veg samosas" exactly like that. It took that so literally that it refused a correct read-back three times and gave up. I reworded the goal so it uses the phrase when ordering without being rigid about it.

A failed scenario can be the agent's fault, the scenario's, or the simulated caller's. The only way to tell is to read the transcript, so I do that for every failure before deciding what to fix. I only change a scenario when the scenario is actually wrong.

In the baseline, the caller had its own way of failing. A couple of times it ended the call right after the agent's read-back, without answering yes or no. The orders were left unconfirmed and counted against the agent. In one of those runs, the agent had also said "I'll read your order back again" and then never called the tool, so both sides dropped the ball. Next time I'll make the report tell these apart: a caller ending the call while the order is still a draft and the agent hasn't ended it should get its own end reason, so the numbers don't quietly blame the agent for it.

## The agent sometimes skips end_call

After saying goodbye, the agent doesn't always call `end_call`. In text mode it doesn't matter, but in a voice call the line would stay open. Every eval run records how the call ended, so I can see how often this happens before touching the prompt.
