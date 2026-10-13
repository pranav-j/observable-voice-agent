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

In the end, fix 1 (ending the turn on a question) already stopped every premature confirm in the runs after it. So the guard went in as a second layer, with no eval run, since there was nothing left to measure. The session counts caller turns, `get_readback` notes the count, and `confirm_order` refuses with `READBACK_NOT_ANSWERED` if the caller hasn't spoken since. It catches the case fix 1 can't: a read-back worded without a question mark. A stale read-back still gets the more useful "the order changed" error, and a fresh read-back needs a fresh reply. The guard lives in the core, so the voice worker gets it by calling `caller_spoke()` on each turn, the same way the text loop does.

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

## Fix 3: the read-back says the pack size

The read-back used to drop bracket notes, so "Veg Samosa (2 pcs)" came out as "Two Veg Samosa". It now speaks the note: "Two Veg Samosa, two pieces each", or "One Gulab Jamun, two pieces" for a single one. The order summary the agent sees uses the same wording, so the agent gets the same cue as the caller. Bracket notes in any other form are still dropped, so nothing odd gets read aloud.

Same two samosa scenarios, ten runs each. The "before" is the search fix's run, so the only difference is this change. It went from 15 of 20 to 19 of 20 ([report](../reports/20261011-092437-text/summary.md)). The plural scenario passed all ten. The failures it was aimed at, the agent recording 2 or 4 where 1 or 2 plates were meant, didn't happen at all. Caller hang-ups mid-order went from 3 to 1, and that one was the simulated caller leaving after a correct read-back.

Across the two fixes, these two scenarios went from 10 to 15 to 19 out of 20. The read-back change came from a decision I made early on, "don't speak brackets", which seemed tidy at the time and turned out to hide information people need.

## Fix 4: spoken phone numbers are parsed in code

In the reference run, the model turned "nine zero zero zero zero, zero zero zero two three" into a nine-digit number and the call ended in a transfer. In an earlier run it invented "0000000000", and that got through validation because it's ten digits. So the phone parser now understands spoken digits: "zero" or "oh" through "nine", the Indian-English "double nine" and "triple zero", and "plus nine one" for the country code. Other words like "my number is" are ignored. A number that still starts with 0 once the prefix is gone is rejected. The tool description now tells the model it can pass the caller's words through as they are, so the counting happens in code.

This is the first fix the eval couldn't show. The before run passed 20 of 20 ([report](../reports/20261011-093445-text/summary.md)). The model usually converts the digits correctly; the failures I'd seen are rare. With no failures to remove, there was no room to show an improvement. The case for this change is the unit tests: code can't drop a zero, and the placeholder can't get through anymore.

The after run was a regression check ([report](../reports/20261011-093800-text/summary.md)). It passed 18 of 20, and the model now passes spoken words straight through in about half its `set_customer` calls, so the parser is doing real work. Both failures were the simulated caller. The agent read back "90000 00025", which was correct, and the caller kept saying "no, it should be 9000000025", which is the same number without the space, until it gave up. That has now happened more than once, so the caller prompt needs to say that numbers are read back in groups. I'll treat that as a measurement fix, with its own run, not mix it into this one.

## Fix 5: an error message that says what to do instead

When a caller asked to swap a latte for a cappuccino, the model tried `update_item` with a new `item_id`. That tool only changes quantity, size and modifiers, so the call failed with a generic "extra inputs are not permitted". The agent then told the caller the swap couldn't be done. The fix isn't to accept `item_id`, because any field in the schema is a field the model will reach for. The fix is the error: it now says "update_item can't change the item itself; call remove_item for this line, then add_item for the new item". The schema the model sees stays the same.

I didn't run an eval for this one. It came up once in 93 runs, so a targeted run would mostly measure luck. What the unit tests check is the part that matters: the message names the recovery, and the order is left alone. It's a small thing, but it changed how I think about tool errors. They're the agent's only instructions at the moment it's stuck, so they should say what to do next, not just what went wrong.

## Second reference, before the voice work

After fixes 2 to 5, the confirm guard and caller prompt v2, I re-ran the whole suite as the reference for everything that follows. Report: [reports/20261011-103854-text/summary.md](../reports/20261011-103854-text/summary.md). It folds in several changes at once, so the per-fix sections above are where individual effects were measured.

Task success was 93.5% (87 of 93), against 94.6% for the previous reference. That's one run, which is noise. What did change: the simulated caller hanging up mid-order went from 2 runs to 0, transfers came out at exactly the 3 expected, and premature confirm attempts dropped from 11 to 4. The caller prompt changes did what they were meant to.

The six failures left are a different kind of problem. In five of them, the agent lost something: an item the caller asked for, a quantity change, or the latte-to-cappuccino swap. The read-back showed the mistake plainly, and the simulated caller said "yes" anyway. In one, the caller had just asked for a cappuccino, heard "one small Cafe Latte", and said "yes, that's correct".

So two things are true. The agent's main weakness now is keeping track of edits across turns, especially after an interruption or a correction. And the read-back only works as a safety net if the person listening actually listens. My simulated caller, on the cheap model, isn't careful enough to play that part well. Scoring still counts these runs as failures, which is right, since the order is wrong. But a real person would probably have caught most of them. A stronger model for the caller would make the harness more realistic, at a higher cost per run. I noted that trade-off when I picked the models, and now there's evidence for it.

## Starting voice: the SDK version conflict

The first thing that broke when I added LiveKit Agents wasn't code. It was dependency resolution. LiveKit Agents 1.8.6 requires the OpenAI SDK below version 3, and my text-mode client was pinned to a 3.x release. Both runtimes have to live in one environment and should really use the same SDK, so text mode moved back to the newest 2.x release. I checked that 2.x had everything the client uses (the "none" reasoning level and the Responses API types), then re-ran everything, including the live test against the real model. Everything passed unchanged. uv also pointed out that my project claimed to support any future Python while LiveKit supports nothing past 3.14, so I capped the range to match.

Before writing the worker I read LiveKit's source for the exact version I'm pinning, not docs or memory, since this library moves fast. That turned up things that would have hurt:

- In dev mode, it quietly defaults to a cloud turn detector and a cloud interruption model. With a self-hosted server, I have to pick the local ones explicitly.
- Tool results go through `str()`, so returning a dict would show the model a Python repr instead of JSON.
- The built-in recorder writes to a temporary folder that's deleted when the session ends, so the recording has to be copied out in the session-end hook.

## The first voice call

The worker wires the same core into LiveKit Agents. The tools are registered from the same schemas and run the same `dispatch`, with OpenAI for speech-to-text, the LLM and text-to-speech, and Silero voice detection plus LiveKit's local turn detector. To test it without a browser, I wrote a small caller script. It gets a token the same way the backend does, joins the room, speaks lines generated with text-to-speech over a real WebRTC audio track (with silence between lines, so voice detection can find the end of each turn), and prints what the agent says from LiveKit's transcription stream.

On the first run, a masala dosa got ordered and confirmed by voice. The order was in Postgres as confirmed, the phone number was read back in groups, and when the agent called `end_call` after its goodbye, the worker hung up and saved the final state. A few things showed up that I want to look at properly rather than tune by feel:

- **Caller lines were split at pauses.** "Hi, can I get one masala dosa please?" came through as "Hi." and then the rest. The worker log said why: the transcript arrived after the turn had already been committed, and LiveKit suggested raising the minimum silence before a turn can end. That's the core trade-off of turn detection: wait longer and the agent feels slow, wait less and it cuts people off. It's exactly what the turn-detection experiment is for.
- **Barge-in works.** My script talked over the agent's phone read-back, and the agent stopped mid-sentence.
- **One agent reply had a sentence repeated.** It might be preemptive generation, where LiveKit starts a reply before the turn is confirmed, or an interruption artifact. Traces should show which.

## Fix 1 again, this time for voice

The second voice call failed the same way the text agent used to. It asked "may I have your name?", then in the same turn said "I'm sorry, I can't complete…" and ended the call. Fix 1 lived in my text loop, and the voice worker doesn't use that loop. LiveKit runs the tool loop itself, and by default it asks the model for another reply after every tool result.

So I moved the rule into the core, where both runtimes can use one definition: which actions wait for the caller's answer, the "waiting for the caller" result, and the question check. In voice, the agent class records the text the model produces in each step. When a tool runs in a step whose text asks the caller something, the final actions are held back, and the tool result tells LiveKit no follow-up reply is needed, so the turn ends there. Running the exact same call again, the agent asked, waited, read back, waited for the yes, and confirmed.

Telemetry was working by then too. Every span LiveKit creates reaches Phoenix tagged with the session id, and each turn's timings go into `turns.jsonl` next to the recording. The first numbers I saw in a dev call were slow, with most of the time spent waiting for the end of the turn, in the LLM's tool rounds and in waiting for the first sentence of speech. I'll only write numbers down once they come from a proper report, but that's where the latency work will start.

## Recording calls, and two ways cost could have read zero

Every call now leaves a folder in `recordings/`:

- LiveKit's stereo recording, plus the caller and agent split into separate WAV files
- the transcript, every tool call with its result, and LiveKit's full session report
- the per-turn timings
- a usage file with the estimated cost

LiveKit records into a temporary directory that it deletes when the job ends, so the copy happens in the session-end hook. The channel split is tested with a synthetic stereo file: a tone on the caller's side and silence on the agent's.

Prices live in `config/rates.yaml`, not in code, and a model with no rate is reported as unpriced rather than counted as free. That rule paid off on the first real call. Everything came out unpriced, because LiveKit reports the provider as `api.openai.com` and my rates file says `openai`. Without the rule, every call would have looked like it cost nothing.

The second catch was quieter. The streaming speech-to-text reports no audio duration at all, so its cost would also have come out as zero, even though it's billed for every minute of audio sent. The caller's audio streams for the whole call, so the call's length is a fair stand-in. When that fallback is used, the usage line says it's an estimate, so a guess never gets presented as a measurement.

## The web UI, and a crash only a real browser could find

The dashboard has a Start call button, a live transcript of both sides, an order panel driven by the worker's updates, a latency overlay, and an end-of-call summary with duration, turns and estimated cost. The overlay shows the last turn as a waterfall (transcript, end of turn, tool rounds, LLM first token, first audio) plus a rolling p50 and p95. The worker publishes each turn's timing record to the room, the same record it writes to `turns.jsonl`, and the same numbers LiveKit attaches to the spans in Phoenix. So the overlay matches the traces by construction, and when I checked a call, every number lined up with both.

To test it without talking into a microphone myself, I ran the real page in Chromium with a WAV file standing in for the mic: a caller script synthesized with text-to-speech, with long pauses for the agent to answer. The first attempt showed a blank page. The browser's error log said React had crashed with "destroy is not a function". My transcript component scrolled to the bottom in a one-line effect, `useEffect(() => el?.scrollIntoView(), [lines])`. That one-liner returns whatever `scrollIntoView` returns, and recent Chromium versions return a Promise from it. React treats an effect's return value as its cleanup function, so it tried to call the Promise and took the whole page down. Typecheck and lint passed, and so did the build. Only running it in a real, current browser caught it.

With that fixed, the browser call went all the way through: ordered, name and number taken, read back, confirmed, and the summary card filled in once the worker saved the call. Speech recognition also wrote the caller's "Meera" as "Mira", and that's the name on the order. That's the kind of thing the name-spelling scenarios will measure once the eval harness runs over audio.

## The simulated caller can be the thing that fails

Two failures in one batch came from my side of the test, not the agent. In one, I'd told the caller to say "two plates of veg samosas" exactly like that. It took that so literally that it refused a correct read-back three times and gave up. I reworded the goal so it uses the phrase when ordering without being rigid about it.

A failed scenario can be the agent's fault, the scenario's, or the simulated caller's. The only way to tell is to read the transcript, so I do that for every failure before deciding what to fix. I only change a scenario when the scenario is actually wrong.

In the baseline, the caller had its own way of failing. A couple of times it ended the call right after the agent's read-back, without answering yes or no. The orders were left unconfirmed and counted against the agent. In one of those runs, the agent had also said "I'll read your order back again" and then never called the tool, so both sides dropped the ball. Next time I'll make the report tell these apart: a caller ending the call while the order is still a draft and the agent hasn't ended it should get its own end reason, so the numbers don't quietly blame the agent for it.

## The agent sometimes skips end_call

After saying goodbye, the agent doesn't always call `end_call`. In text mode it doesn't matter, but in a voice call the line would stay open. Every eval run records how the call ended, so I can see how often this happens before touching the prompt.

## Testing over real audio

Text mode can't tell me anything about timing, noise or speech recognition, so the audio harness puts a simulated caller into the LiveKit room as a real participant. The same LLM caller decides what to say. A second layer turns it into speech with a persona's voice, mixes in cafe or street noise at the scenario's signal-to-noise ratio, sends it over a WebRTC track, and listens to whatever comes back.

All timing is measured from the caller's side, from the audio it actually receives. The agent already reports its own timings to Phoenix, but a harness that trusts those only confirms what the agent believes about itself. Agent speech is found with a plain energy threshold. The agent's audio is clean synthesized speech, so a level threshold is enough, and it gives the same answer every time I re-run it on saved audio. The settings are written into every report.

Two things broke before a single call finished. First, text-to-speech read the fake phone number 9000000002 as one big number instead of digits. The caller now spells long digit runs out in groups of five, the way a person reads a number. Second, the caller sometimes sat waiting until the agent's idle timeout fired. Single loud frames in the agent's silence kept resetting its "agent is still talking" clock. The live tracker now uses the same rule as the offline detector: speech only counts after a short unbroken run of it.

## Repeated tool calls, and the bug wasn't in my code

In one audio call, the agent searched the menu twice for the same thing, then added the same coffee three times. LiveKit hit its tool-step limit and the agent told the caller it was "having trouble processing the quantity". Text mode never did this with the same model, prompt and tools.

The tool log showed the calls were sequential, one per LLM step, so the model was acting as if it hadn't seen its last result. The spans in Phoenix showed what each step sent: after the first step, only the new tool call and its output, chained to the previous response with `previous_response_id`. Those responses are stored on OpenAI's side, so I fetched the exact input the server used for each one. Every tool call was in there twice, once from the previous response's own output and once more because LiveKit's plugin sends it again, followed by a single output. The model sees two calls and one answer, and sometimes makes the "unanswered" call again.

A small script driving the plugin directly with the same history sent the same doubled items, but the model coped there. So this is intermittent, which is exactly why it showed up only once. The fix is one setting: `store=False`, so every step sends the whole conversation instead of chaining. That's what my text loop already does, and nothing about the call is kept by the provider. After the change, the calls I ran made each tool call once.

Earlier I'd suspected preemptive generation for some doubled sentences in the transcripts. With this fix in and preemptive generation on, I haven't seen it again. I'll watch for it in the suite runs before deciding anything about that setting.

## The caller hung up in the middle of the read-back

The next call failed differently. After "Yes" to the phone number, the agent started the read-back, and the simulated caller hung up halfway through it. The caller treated a little over a second of silence as the end of the agent's turn. In a long reply there's a gap between sentences while the next one is synthesized, and that gap can be longer. The agent's transcript only arrives once the whole utterance has been spoken, so the caller found nothing to reply to and ended the call.

Now the caller waits for silence and for the agent's transcript stream to close. If a stream never closes, a longer silence still ends the wait. This was a harness bug that would have been scored as an agent failure, which is the worst kind, because nothing in the agent needed fixing.

## Phone numbers said in two halves

With the harness fixed, a real agent weakness showed up. The caller says the number in two groups of five with a pause in between, like people do. The turn detector ended the caller's turn at the pause, so `set_customer` got "nine zero zero zero zero", rejected it, then got "zero zero zero zero two" and rejected that too. After a few rounds the agent handed the call to a person.

Joining the parts is counting, and counting belongs in code. `set_customer` now holds a partial number and joins it with the next part. If the parts add up to a valid number, it's used. A whole number on its own replaces whatever was held, and too many digits drops the held part. While a number is incomplete, the tool says how many digits it has and tells the agent to say something short like "okay, go on". The agent still reads the full number back, so a wrong join gets caught on the call.

The calls are also slow. The caller-side latency on these runs is far beyond what a phone call can feel natural with. Speech-to-text, end-of-turn detection, a separate LLM round for each tool and text-to-speech all add up. I'll write numbers down once they come from a proper report. That's the next big piece of work after the harness.

## The fake phone numbers were the hardest case

Every scenario used a number like 9000000014, which keeps them obviously fake. Over audio, that's about the worst number you can pick. Speech recognition can't count a long run of "zero zero zero zero", and it kept dropping one or two. So most audio failures were really about that one fixture choice, not about anything the scenario was meant to test.

The numbers still start with 90000, so they're still obviously fake, but the second half now varies, like 90000 26457. One scenario keeps a number that's mostly zeros on purpose, so that weakness gets measured on its own instead of leaking into every result.

The same runs showed a problem with how I'd taught the agent to handle partial numbers. When digits went missing under noise, the agent asked for "the last two digits". But the caller had said the whole number, and the dropped digits were from the middle, so the caller supplied the end and the join glued it in the wrong place. Now the agent reads back what it has and asks for the whole number again. If the caller carries on with the rest instead, the code still joins the parts.

## Fetched isn't the same as heard

This one would have been bad in production. The caller said "Yes, that's right" with a little pause in the middle, so it arrived as two turns. On "Yes", the agent fetched the read-back. "That's right" then interrupted it before a single word played. And "that's right" counted as the caller's answer to the read-back, so the order was confirmed without the caller ever hearing it.

The rule in code said a read-back had to be fetched after the last change, and the caller had to speak after that. In text mode, fetching and showing are the same thing. In voice they aren't. Now the runtime tells the session what the agent actually finished saying, with a flag when the caller cut it off. A read-back only counts once most of its words have been said, in order, without an interruption. The confirm tool explains which case it is, so the agent knows to say the read-back again rather than just wait.

I would not have found this with text evals or unit tests. It took a simulated caller with a realistic pause in the middle of a sentence.

## Preemptive generation goes off

With preemptive generation on, the agent sometimes said the same sentence twice: "May I have your name for the order? May I have your name for the order?" The caller's transcript, which follows what's actually played, had it twice too, so the caller heard it. Every time I saw this, preemptive generation was on, and I haven't seen it with it off. It's off by default now. It exists to cut latency, so the latency experiments will measure what it actually saves. If that's worth having, I'll find out why it doubles before turning it back on.

## Smaller harness fixes

- The scripted pause in the "pause while giving the phone number" scenario was tied to the caller's third turn. A hesitant caller reached the number later, so the pause landed on "No, that's all". Pauses can now be tied to the phone number itself, and they go between its two halves, the way people actually pause.
- The simulated caller accepted "Riddle" as its own name in a read-back. Its prompt told it to check the order, not its own details. It checks its name and number now.
- "Okay, go on" confused the simulated caller. In replays it hung up, said "that's all", or even answered as if it were the restaurant. Reading back the digits so far worked every time, and it's what a person taking the call would do anyway.

## The first full audio run, and what it turned up before the credits ran out

The first full audio suite stopped partway through: the API account ran out of credit, and every call after that failed. The runs before that point were real, though, and reading their transcripts was worth it. I'm not quoting numbers from it, because it isn't a complete report.

**A read-back flagged as interrupted that wasn't.** Several calls ended with "Yes, that's correct. Goodbye." and the agent saying the order wasn't confirmed. My new rule had refused it: LiveKit marked those read-backs as interrupted. But each one held the full text and had finished playing long before the caller spoke. In the same step, the model had also tried a tool call that the turn rule held back, and that kept the speech open until the caller's next words arrived. Then LiveKit flagged it as interrupted. So the flag doesn't mean "the caller cut it off". What matters is the text, because LiveKit trims an interrupted message to what was actually played. A read-back now counts if the played text reaches its last words. I replayed every read-back from those runs through the old and new rule. The new one accepts the falsely flagged ones and still refuses the barge-in scenarios, where the caller really did cut in.

**Voice had a lower tool limit than text.** LiveKit stops after three tool steps in a turn unless told otherwise. A two-item order can need four, so the agent was sometimes forced to answer halfway through, with no tools allowed. Both runtimes now use the same limit.

**Names spelled out loud were still lost.** Speech recognition wrote Kavya as "Caviar" and Nikhil as "Nick Hill", and kept doing it even after the caller spelled the name. The letters were right there in the transcript. A name given as single letters is now joined in code, and the tool tells the model to pass spellings through as letters.

**Yes and goodbye in two turns.** "Yes, that's correct." and "Goodbye." arrived as separate turns, and the agent answered the goodbye by ending the call, forgetting the yes. Now the first `end_call` after an answered read-back, with the order still unconfirmed, is held with a reminder to confirm if the answer was yes. If the caller really wants to stop, calling it again ends the call. None of these fixes have been measured yet. They need the next run.

## Seeded faults, recorded calls and the judge

To show the harness catches what it claims to, the worker takes a `FAULT` setting that breaks one thing on purpose: barge-in turned off, modifiers silently dropped by the voice tool layer, end-of-turn silence cut to 150 ms, or an extra delay before the LLM's first token. The faults live in the voice layer only, and each call's saved settings record which one was on. The validation runs themselves are still to do.

Recorded mode scores real calls. I make a call from the browser, and `make annotate` starts a file with the agent's final order, which I correct to what I actually wanted. That's the point: the agent's version is only a starting place. Timing for those calls comes from the worker's two-channel recording, with the same detector as the audio evals, so it's measured at the agent's end and leaves out the network.

The one judge-based metric, whether the agent owned up when an action failed, runs as a pass over a finished report rather than inside the calls, so it can be redone when the judge prompt changes. Two things came up while building it. In text mode, most "errors" were the agent saving the name with a blank phone number before asking for the number. Nothing went wrong from the caller's side there, so those don't count, and the judge would have passed them anyway, which flatters the score. And a random calibration sample was almost all one kind of error, so the sample now takes from each error type in turn. The agreement with my hand labels shows up in reports only for the judge prompt version it was measured on.

## Restarting the audio run, twice

With credit back, I ran a short check before the full suite, and it found a harness bug. The caller's last line, "Yes. Goodbye.", went out as a fraction of a second, and the agent never heard it. Out of a few hundred caller lines it had happened once. I couldn't tell whether text-to-speech had returned clipped audio or the frames had gone out too fast, so I guarded both. Clipped speech is retried and, if it stays clipped, the run is marked as a harness error. A line that goes out much faster than real time also counts as a harness error. Either way, the agent doesn't get blamed for something it never heard.

A few calls into the full run, two failures in the same scenario showed the phone fixtures were still a problem. I'd already moved the numbers off the long run of zeros, but the remaining "nine zero zero zero zero" still lost a zero most of the time, and one call ended in a transfer over it. So the numbers now start with 98765, the placeholder most Indian developers would recognize, and the second half has no repeated digits. One scenario still uses a run of zeros, and a test makes sure it's the only one. I stopped the suite, since a baseline that mostly measures one fixture choice is worse than losing a few minutes of calls.

The same calls showed the agent setting "Nick Hill" as the name three times in a row while the caller kept saying "Nikhil". Speech recognition heard it the same way every time, so asking again was never going to work. Setting the same name and number again now comes back with a note telling the agent to ask for a spelling. The spelled-name join from earlier then does the rest. In the short check afterwards, the caller spelled it once and the order went through with the right name.

## A gate for the evals

Unit tests can't catch a change that makes the agent worse at its job. So there's now a gate: a reviewed report becomes the baseline, and a later report fails if any key metric is worse by more than its margin. Pass rates use an absolute drop, latency a relative rise, and error rates an absolute rise. If one side didn't measure a metric, the gate says it skipped it rather than quietly passing. The margins are set loosely for now, because the same build gives different numbers from run to run, and a gate that fails at random gets ignored. They'll come down once repeat runs show how big that spread is.

Pull requests run the text suite and the gate when the API key secret is set. The audio suite runs only by hand, since it needs a LiveKit server and a worker and costs real money. `make compare` puts two reports side by side. That's what the before and after tables for experiments and seeded faults will come from.

## Text mode after the voice fixes

Most of today's fixes came from voice calls, but they live in the shared core, so I re-ran the text suite to check they didn't break anything there. Task success went from 87 of 93 in the previous reference to 90 of 93 (reports `20261011-103854-text` and `20261011-152337-text`). One run is noise at this size, but three in the right direction, with no new failure types, is what I wanted to see.

The early-confirm count went up. That's how many runs had the model saying the read-back and calling `confirm_order` in the same step. The turn rule holds every one of those back, so no order was confirmed early. The count is about the model trying, and I'll keep an eye on it.

Two of the three failures weren't really the agent's fault. In one, the model returned an empty reply right after fetching the read-back, which happens rarely. In the other, the simulated caller contradicted its own scripted line: it said "make that a cappuccino instead", then later insisted it wanted the latte. The fix for the caller is to keep scripted changes in its instructions, not just its history. I'm holding that until the seeded-fault runs are done, since those compare against the audio suite running now, and changing the caller in between would muddy the comparison.

## The third restart: two more harness bugs, and a call that ran out of time

The next attempt at the full run looked bad early: seven of the first sixteen calls failed, and three of those were the simulated caller hanging up mid-order. That pattern usually means the harness, so I read those calls before letting the suite go on.

Two were the harness. In one, the caller's "Pooja." went out as 0.3 seconds of audio and the agent never heard it, the same failure as the clipped goodbye. My clipped-speech check allowed 0.2 seconds per word, and a one-word line passes that. Normal output, even for "Yes.", is over a second long with its silences, so lines now need at least 0.6 seconds.

The other was the same root cause as the read-backs flagged interrupted. When the agent asks something and the turn rule holds back a tool call in the same step, LiveKit keeps that speech open until the caller talks. The agent's transcript stream stays open too. So the caller waited, gave up on the stream, found no finished transcript, decided the agent had said nothing, and hung up. The caller now reads the stream as it arrives and uses the text so far if the stream never closes. Each line is also timed from when the agent started it, so a stream that closes late doesn't leak into the next reply.

The third was the agent. Every time the caller corrected a misheard name (Garev, then Garov, then Garav), the agent also read the phone number back again, which cost a turn each time, and the call hit the five-minute limit. The number is only read back now when it actually changed. A name correction also tells the agent to ask for a spelling if it's still wrong. And calls that hit the time limit now say so, instead of being labelled as running out of turns.

I stopped the run again for these. A baseline that blames the agent for harness bugs would be worse than no baseline. From here the suite runs to the end unless the harness itself breaks.

## The fourth restart: the agent's own counting, and "that's all"

The next attempt turned up two real agent bugs and the caller bug I'd been putting off.

The agent saves the name with a blank number before it asks for the number. That used to come back as an invalid phone number. The prompt tells it to hand over to a person after three failed tries at the same step, so in one call it counted those blank saves and transferred the caller before they'd said a single digit. A missing number now has its own result, which says plainly that it isn't a failed attempt.

In another call, the agent asked "Anything else?", the caller said "No, that's all, thank you", and the agent ended the call with nothing saved but the biryani. The hold I'd added for `end_call` only covered the moment after a read-back. Now it covers any unplaced order that has items: the first `end_call` gets held once, with a hint about which situation it probably is. A caller who really wants to leave still can.

The caller bug was the simulated caller disowning its own scripted lines: "add a gulab jamun too", then later "I didn't ask for gulab jamun". I'd held this fix until after the fault runs, so they'd compare against the same caller. But it was hurting the baseline itself, and fixing it before the baseline keeps that comparison fair anyway. Caller prompt v4 lists the scripted lines it has already said and tells it they're part of what it wants now.

After the fixes, the four scenarios that had failed each passed a check run, and the full suite is running again. The text suite is running alongside it with the new caller, so both reports use the same one.

## The first full audio baseline

The suite finally ran to the end: 85 of 93 runs passed (`reports/20261011-163931-audio`), and that report is now the audio baseline for the gate. The latest text report is the text baseline. The numbers that matter most for what comes next are timing. Caller-side response latency is 6756 ms at p50 and 10284 ms at p95, so every measured turn counts as dead air. Barge-in stops at 917 ms at p50. Cost works out to $0.024 per minute on the agent's side. Nothing in the agent has been tuned for speed yet, and that's the next piece of work.

Two things in the report changed what I thought I knew.

**Doubled sentences aren't caused by preemptive generation.** The report counted seven replies with the same question said twice, with preemptive generation off. I'd turned it off because of exactly this, and written that I hadn't seen it with it off. That was wrong, and I've corrected the ADR. Every one of the seven came right after the caller's turn arrived in two pieces, like "No." then "That's all.". The calls where the agent never heard the caller's next short line also came after a split turn. LiveKit warns that the transcript arrived after the turn was already committed, and suggests waiting longer. So the end-of-turn wait looks like a correctness setting as well as a latency one, and I'll test it in both directions.

**The judge was grading silence.** Error acknowledgement first came out at 13 of 21. All eight misses had no reply at all. That was mostly the agent correctly saying nothing while the caller finished reading out a number. The judge marked those as failures to communicate, but there was nothing to grade. Silence after an error is now counted on its own and kept out of the rate.

The calibration file for the judge is ready: twenty real cases from the reports, plus five I constructed where the reply claims success. Nearly every real reply handled its error well, so without the constructed ones a judge that always said yes would look perfect. The labels have to come from a person.

## Breaking the agent on purpose

I ran each seeded fault against the scenarios it should affect and compared the results with the same scenarios in the baseline. The full write-up is in `docs/harness-validation.md`. Two faults were caught straight away. Dropping modifiers took exact match from perfect to zero. Slowing the LLM pushed p95 latency up 44%, well past the gate margin.

The other two found problems in my harness, which is what this exercise is for.

**The barge-in metric was measuring the wrong thing.** With barge-in switched off, the agent talks straight over the caller, so its stop time should explode. Instead it got *faster*, 917 to 207 ms. The metric stopped the clock at the end of the agent's current speech segment, and segments end at every pause between sentences. An agent that ignores you finishes its sentence, pauses, and keeps going, and the metric only saw the pause. Now it runs to the end of the agent's reply. Because every run saves its audio, I re-scored the baseline and every fault report without making a single call. The fault now shows up as about 17 seconds instead of under one, and the baseline barely moved.

**The end-of-turn fault couldn't break the agent.** Cutting the silence wait to 150 ms changed nothing, because the semantic turn detector holds the turn when a sentence sounds unfinished. Good for the agent, useless as a test. With the turn model removed as well, it did break: task success fell from 89% to 33%. But the false cut-off metric still read zero. It counts agent audio that starts during the caller's pause, and with replies taking about six seconds, the audio never started until the caller had finished, even though the turn had already been cut. That metric only becomes meaningful once replies are faster than a pause, and I've written that down as open.

One more thing went wrong overnight. The Mac went to sleep on battery partway through a fault run. The worker's sessions stayed open through it, and four two-minute calls were costed as more than an hour each, because speech-to-text cost is estimated from call length when the provider doesn't report it. The estimate now uses the length of the recorded audio, which doesn't grow while the machine sleeps, and long runs now keep the Mac awake.

## First latency levers, and moving speech off the bill

The first two latency changes were measured on six scenarios at three runs each, compared with the same scenarios in the baseline.

**Raw audio from text-to-speech instead of MP3** (`reports/20261012-001531-audio`). The agent's own timings show it worked, but only a little: time to first audio went from 1.10 to 1.00 seconds at p50. The caller-side latency didn't move. In the same run, the LLM's first token came 0.3 seconds later than in the baseline, which is just the provider having a slower hour, and that swamped the gain. That's why reports now carry the agent's per-stage timings next to the caller-side ones: one number can't tell a faster stage from a slower one hiding it. Raw audio stays on, since it's a small gain for nothing.

**Filler phrases** (`reports/20261012-021611-audio`). The agent said "One moment." when a reply needed tool calls. Caller-side latency fell from 7.0 to 4.2 seconds at p50. But that's partly accounting, since the filler itself counts as the start of the reply, and task success halved. The simulated caller answered "One moment." with "Sure.", and that "Sure." became a turn of its own. Then came the doubled questions and confusion I'd already seen after split turns. A real person might well say "okay" too. Fillers are off.

Then the budget ran low. Most of the cost was speech: in the baseline, recognition was 62% and the two voices 37%, while every LLM call together came to about 1%. So speech is moving to local models: Whisper (`faster-whisper`) for recognition and Kokoro for both the agent's and the caller's voices, the same Kokoro I used for the narration in another project. The LLM stays hosted, because the agent depends on reliable tool calls. Both pipelines stay switchable by setting, and reports record which one ran. The local pipeline will get its own baseline, since a different recognizer and different voices make it a different system to measure.

## Is local speech good enough?

Before wiring anything in, I checked whether local Whisper could hear the callers well enough. The numbers here are in `reports/20261012-offline-speech`, together with the scripts that produced them. Every recent run had saved each caller line exactly as sent, so I ran Whisper over 521 of them and scored the results against the scripts. The `base.en` model got 12.8% of words wrong at 0.35 seconds per line, and `small.en` got 10.9% at 1.44 seconds. Over the same calls, the hosted recognizer had a 15.4% error rate as the agent heard it live. That comparison favours Whisper: it got the clean audio as sent, while the hosted model got it after the network, with noise mixed in on noisy scenarios, and its figure includes lines it never heard at all. So I don't read it as Whisper being better, only as good enough. `base.en` is the default, because waiting 1.4 seconds after every caller sentence would undo the point.

Kokoro takes 0.3 to 0.5 seconds to synthesize a short first sentence on the M4, against about a second for the hosted voice to start. In a two-call live check with everything local, the agent's first audio came at 0.57 seconds instead of 1.1, and the calls cost $0.002 in LLM tokens and nothing else. The catch was the end of the turn: it got slower, from 0.58 to 1.03 seconds, because Whisper only starts once the caller has stopped speaking. And names were harder. "Ritu" came out as "Redwood".

Three fixes that had been waiting for a clean moment went in before the local baseline:
- **Re-fetching the read-back no longer throws away the caller's yes** when nothing has changed. The agent used to re-fetch after "Yes, that's correct. Goodbye.", couldn't confirm, and the caller was gone.
- **Clearer pack wording.** The read-back now says "One Gulab Jamun, which comes as two pieces" instead of "One Gulab Jamun, two pieces", which a caller heard as the wrong quantity.
- **A simulated caller that hangs up on a read-back without a word is asked once more,** since that breaks its own instructions.

## Two more harness bugs, both from going local

The first try at the local baseline stopped early on a familiar-looking error: "text-to-speech kept returning clipped audio for 'Neha.'". It wasn't clipped. Kokoro returns just the speech, with none of the silence OpenAI's voice leaves around each line, and a one-word name came out shorter than the floor I'd set to catch clipped lines. The caller now leaves a little silence before and after each Kokoro line, the way a person does. The floor still catches audio that really is broken.

The second try died differently: "BadZipFile: Overlapped entries: 'hm_omega.npy'". Both simulated callers in a run share one Kokoro model, and Kokoro reads its voices lazily out of a zip file. Two threads reading the same zip at once corrupted the read. Calls into each local model now take turns. I checked the fix with three threads hammering one shared Kokoro before restarting.

The partial runs also showed the local pipeline's real weakness: names. "Nikhil" became "Nick Hill" every time, and "Pooja", "Neha" and "Imran" came out as "Pooj", "Nihal" and "Imrn". `base.en` is an English-only Whisper model listening to Indian names spoken by Kokoro voices, and that combination is hard. The full baseline will show how much it costs, and a multilingual model or a short context prompt for Whisper are the obvious things to try next.

## The caller's voice was failing the test

The first full local-speech run passed 64 of 93 (`reports/20261012-050510-audio`), against 85 for hosted speech. Replies started a quarter sooner, from 6.8 to 5.0 seconds at p50, and the agent's speech cost nothing. But 27 of the 29 failures were names or phone numbers.

Before blaming Whisper, I tested it offline, which costs nothing. These results are in `reports/20261012-offline-speech` too. Kokoro spoke names, spelled names and phone numbers in the six caller voices, and I ran four Whisper variants over them, with and without a context prompt. Every English model got all twelve phone numbers right, so those failures came from the calls themselves, like numbers split across turns. Names were bad whatever I tried: between 5 and 10 of 18.

Then I ran Whisper on names spoken by OpenAI's voices, which I had saved from earlier runs. `base.en` got 16 of 21 and `small.en` got 19 of 21. The same recognizer got about twice as many names right. Kokoro reads Indian names through an American-English pronouncer and mangles them, so a lot of what looked like the agent mishearing was the simulated caller mispronouncing. It's the same lesson as before: check the harness before blaming the agent.

So the fair local setup keeps the agent on local speech and gives the simulated caller OpenAI's voice. The caller's voice was only about a tenth of the cost, so a full run is about a dollar, and that run is now the local baseline. The Kokoro-caller report stays as a record of what an unrealistic caller does to the numbers.

## Local speech, with a caller that sounds right

With the agent on local speech and the simulated caller back on OpenAI's voice, the full suite passed 85 of 93 (`reports/20261012-072648-audio`). That's the same count as the hosted baseline. Replies started at 4.9 seconds at p50 instead of 6.8, the agent's speech cost nothing, and doubled replies fell from 7 to 3. It isn't a perfectly clean comparison: three agent fixes went in between the two runs. But it was enough to make local speech the default. OpenAI's speech is still one setting away.

The stage timings show where the time moved. The voice starts 0.4 seconds sooner, and the end of the turn takes 0.3 seconds longer, because voice detection has to decide the caller has stopped before Whisper can start. So that silence setting is the next lever.

Two of the eight failures were the agent saving "Puja with two Os" and "Mira with two Es" as names. A description of the spelling is now rejected as a name, and the tool says to pass the name spelled that way.

## The last latency levers, and the gate doing its job

Two more levers on local speech, each against a fresh run of the same six scenarios on the same code.

**Cutting voice detection's end-of-speech silence from 550 to 300 ms** made the agent's own end of turn 0.3 seconds faster, but callers didn't hear back any sooner. And the agent started answering into a caller's mid-sentence pause. That was the first time the false cut-off metric moved: replies are finally fast enough to land inside a pause. Rejected.

**Preemptive generation** came back. It took caller-side latency from 5106 to 4761 ms at p50 and from 8483 to 7157 ms at p95, and the one doubled reply in 18 calls is about the rate I'd been seeing without it. All told, these six scenarios now answer about 2.1 seconds sooner at the median than at the start, and 3.3 seconds sooner at p95. Every turn still counts as dead air, though, and what's left is mostly LLM round trips. Fewer tool steps per turn would be the next thing to try.

The gate fails the slow-LLM fault run, on both p95 latency and task success, and exits non-zero. Showing it on an actual pull request needs the API key added as a GitHub secret.

## Limits before anyone else can call it

A public demo needs limits, since every call costs a bit of LLM and ties up the CPU that runs the speech models. Calls already end after five minutes. Now `/token`, where every call starts, can also refuse a call past a per-IP hourly limit or a daily total, with a message the web page shows. Both are off unless set, so they don't get in the way of the evals.

The one thing I almost got wrong was the caller's address. Behind a hosting proxy, the real address comes in `X-Forwarded-For`, and I nearly took the first entry. But the client can send that header itself with anything in it, and the proxy only appends. So the first entry is whatever the client wants it to be, and the last one is the one the proxy actually saw. There's a test for exactly that.

The counts live in memory, so a restart resets them. For a single demo instance that's an acceptable worst case. Nothing is deployed yet, so none of this has met real traffic.

## The pause scenarios weren't testing the turn detector

I wanted the turn-detection experiment to show how often the agent cuts a caller off mid-sentence, and the false cut-off metric wasn't up to it. It only counts a cut-off when the agent's audio starts before the caller finishes, and with replies taking four or five seconds, that almost never happens. So I added a count from the agent's side: did the agent end the caller's turn while the caller was still in the scripted pause? The agent logs when the caller stopped and how long it waited before ending the turn, and I line its clock up with the caller's on the greeting, which both sides record.

One trap there. I first used each turn record's `created_at` as the moment the turn ended. With preemptive generation on, LiveKit keeps the message it made for the early reply, so `created_at` can come before the turn actually ended. Stop time plus end-of-turn delay is the reliable one.

Re-scoring the saved runs with it was a surprise. With the turn detector on, the agent ended the turn inside the pause in 6 of 9 pauses on the hosted baseline and 6 of 9 on the local one. Turning the detector off on purpose, with the aggressive end-of-turn fault, came out the same: 4 of 6. The transcripts make it obvious: "Hi, um, could I get?" went in as a whole turn, and the rest of the sentence came a few seconds later as another.

The traces showed the detector had run and rated those half sentences as finished. It listens to the audio, not the words. And the simulated caller made each half separately: for a pause, it synthesized "Hi, umm, could I get" as its own line, and the second half as another. A line synthesized on its own ends the way a finished sentence ends, so the detector was right. A person who stops to think in the middle of a sentence doesn't sound like that.

Now the caller synthesizes the whole line once and cuts the pause in at the quietest moment near the split. I checked it offline with the same detector model on 41 paused lines in three Kokoro voices (`reports/20261012-pause-prosody`). Pauses that sounded finished went from 52 of 123 to 17 of 123. Real line endings came out at 86 of 123, so the detector does hear the difference.

It's the same lesson again: before blaming the agent, check what the harness actually sent it. It also means every result I had on hesitation, including the aggressive end-of-turn fault looking caught only by task success, was measured with a broken test. The turn-detection experiment is running again on the fixed caller.

## Turn detection, on a caller that sounds right

With the caller fixed, I ran the turn-detection sweep again on the three hesitation scenarios: LiveKit's turn detector at its 500 ms minimum, and silence alone at 300, 600, 1000 and 1500 ms. Nine scripted pauses each (`docs/experiments/E3-turn-detection.md`).

The detector split none of the nine sentences. Silence alone split all nine at every setting up to 1000 ms, and five of nine at 1500 ms, where the 1.2 s pauses and one of the 1.5 s ones survived. A pause long enough to think in is longer than any silence threshold you'd want on every turn, so on silence alone there's no good setting. The detector costs very little at the median, 0.95 s to end a turn against 0.90 s. Its cost is the tail: when it thinks you're not done, it waits 2.5 seconds. In these runs that hit one-word names and phone numbers, which come up in every order.

Two smaller things I learned on the way. The 300 and 600 ms settings behave the same, because Whisper can't start until voice detection has heard 550 ms of silence. And my first version of the split count missed some splits. The agent sometimes ended the turn a few hundred milliseconds after the pause was over, before it had heard enough of the caller's next word to notice. The phone number still arrived as two turns. Now the count looks at where the caller's speech stopped and whether the turn ended before the sentence did, not at whether the commit fell inside the pause.

I also re-ran the aggressive end-of-turn fault on the fixed caller. It split six of six sentences, so the harness catches it with the metric meant for it. Before the fix it only showed up in task success, and on this run task success didn't separate it at all.

Then the network dropped in the middle of the sweep, and one setting's calls all failed with connection errors. I threw that report away and ran it again rather than keep a run that measured my Wi-Fi.

## The full run, and the agent asking the same question twice

I ran the whole suite again on the current defaults: local speech, preemptive generation on, and the fixed pause scenarios (`reports/20261012-224542-audio`). It passed 86 of 93, with replies starting at 4.6 seconds at p50 and 8.5 at p95. That's the best full-suite result so far, but two numbers needed a closer look before I'd call it a baseline.

**Doubled replies went from 3 to 12.** My first guess was preemptive generation, which was the one thing switched on. But the earlier runs without it had the same thing, 3 and 7 times, and in every case it looked the same: one question twice with no space, "What name should I put on the order?What name should I put on the order?". I cut the agent's audio out of a few of those calls and ran Whisper over it, and the caller really did hear it twice. The traces showed it came out of a single LLM response, not two steps glued together. The model sometimes returns the same text as two message items, a draft and a final answer, and the LiveKit plugin speaks the text of both. It only learns which one is the draft after the text has gone out. So now a sentence that's identical to the one right before it in the same reply is dropped. Text-to-speech waits for whole sentences anyway, so this costs no time.

**The pause scenarios still split sentences 5 times out of 12.** Two were real: a pause in the middle of a phone number, which the turn detector heard as finished. The other three were the harness again. The pause goes halfway through the caller's words, and in short lines like "Great. Thanks." that's between two sentences. Ending the turn there is fine. The pause now goes in the middle of the longest sentence.

One call failed because the agent never showed up, and that one was my fault. A LiveKit worker tells the server it's full when its CPU is busy, and the server then doesn't send it new calls. I was running the test suite in another folder at that moment, on the same laptop. On a server that would mean a caller sitting in silence, so the web page now gives up after 20 seconds and says the agents are busy.
