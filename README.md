# finnbruktbil

A repository for exploring car ad listings on Finn (for personal use).

The repository has three main "modes":
- Fetch ad ids
- Download ad details
- Analyze results

Ad ids can be extracted from manually downloaded html source code, or scraped from an established search. Ad details are scraped from ads and inserted into a Supabase database.

Finally, all ads can be analyzed with the analysis tool, which attempts to match a regression line between "usedness" and price. This is a poor approach if the age span is large, but for narrower age spans, it is not half-bad, and it is very interpretable since it provides a _cost per km_ and a _cost per time since registration_

https://github.com/user-attachments/assets/ab67db7d-5ee5-4987-b090-3dc1236e5826

It is also possible to color by a categorical value, like the number of tire sets included. 

https://github.com/user-attachments/assets/69facad5-1dc5-4ec2-a33c-2b3eabf96aeb

_"tire_sets" is not a structured data type from the ad, but something that is found by doing a content analysis with the `openai` API_

## Tech stack

- Web scraping of dynamic web sites with Selenium
- Web scraping of static web sites with bs4
- Text analysis with LLMs (`openai` API)
- Database management with Supabase
- `uv` and dev environment handling
- Analysis tool with `streamlit`
- General data wrangling with `pandas` and plotting with `plotly`
