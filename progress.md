## Id scraping:
- ⬜ Handle multiple base URLs in a meaningful manner
- ⬜ Read URLs from file instead of hard-coded into script


## Car scraping

Script for scraping the desired data from a specific ad

- ⬜ Use chatgpt/copilot to create selenium scraper for the ad. Scrape as much data as possible, since the bottleneck is on fetching the data, not processing and storing it. Make sure to get the last modified time stamp.
- ⬜ Update raw database. There are two tables:
  - ⬜ Scrape results. Time stamp and list of fetched ids for this "round"
  - ⬜ Fetched data. Time stamp and list of data entries. Only changed ids are stored.
- ⬜ Create snapshot database. Convert the raw database into a snapshot of the current ads. This disregards any history, but it is easier to work with, at least in the beginning.


## Analysis

Script/notebook for analyzing results

- ⬜ For a specific brand and model, plot the price vs age and milage.
