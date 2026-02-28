You are implementing a single story from an implementation plan. Your job is to complete
the story, make all tests pass, and commit the result. Do not move on to other stories.

## Your Story

{story_text}

## Success Criteria

1. All tests referenced in the acceptance criteria pass: `pytest tests/ -v`
2. No existing tests are broken.
3. You commit your changes with a message: `feat({story_id}): <brief description>`
4. You output the line `STORY_COMPLETE: {story_id}` as your final output.

## Failure Protocol

If you reach the end of your context before all tests pass:
1. Commit whatever working code you have: `git add -A && git commit -m "wip({story_id}): partial - context exhausted"`
2. Write a brief summary of what you completed and what remains.
3. Output the line `STORY_RETRY_NEEDED: {story_id}` followed by your summary.
4. Stop.

Do not fabricate test results. Do not mark anything complete unless `pytest` output shows it passing.
{retry_section}
