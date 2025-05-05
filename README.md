# ebird explore

This is a small app that compares local observations with eBird life list with the goal of being able to see what birds are missing from your life list.

## Run

```bash
uv run download_lists.py --login --output-dir ./my_bird_lists
uv run check-and-mail.py
```

## Steps
1. download lifelist (from non public eBird account)
2. download local observations (from public eBird account)
3. compare the two lists
4. send email with the missing birds