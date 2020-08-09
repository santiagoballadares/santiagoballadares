from python_graphql_client import GraphqlClient
import httpx
import json
import pathlib
import re
import os

root = pathlib.Path(__file__).parent.resolve()
client = GraphqlClient(endpoint="https://api.github.com/graphql")


WORKFLOW_TOKEN = os.environ.get("WORKFLOW_TOKEN", "")


def replace_chunk(content, marker, chunk, inline=False):
  r = re.compile(
    r"<!\-\- {} starts \-\->.*<!\-\- {} ends \-\->".format(marker, marker),
    re.DOTALL,
  )
  if not inline:
    chunk = "\n{}\n".format(chunk)
  chunk = "<!-- {} starts -->{}<!-- {} ends -->".format(marker, chunk, marker)
  return r.sub(chunk, content)


def make_query(after_cursor=None):
  return """
query {
  viewer {
    repositories(first: 100, privacy: PUBLIC, after:AFTER) {
      pageInfo {
        hasNextPage
        endCursor
      }
      nodes {
        name
        description
        url
        releases(last:1) {
          totalCount
          nodes {
            name
            publishedAt
            url
          }
        }
      }
    }
  }
}
""".replace(
    "AFTER", '"{}"'.format(after_cursor) if after_cursor else "null"
  )


def fetch_releases(oauth_token):
  repos = []
  releases = []
  repo_names = set()
  has_next_page = True
  after_cursor = None

  while has_next_page:
    data = client.execute(
      query=make_query(after_cursor),
      headers={"Authorization": "Bearer {}".format(oauth_token)},
    )
    print()
    print(json.dumps(data, indent=2))
    print()
    for repo in data["data"]["viewer"]["repositories"]["nodes"]:
      if repo["releases"]["totalCount"] and repo["name"] not in repo_names:
        repos.append(repo)
        repo_names.add(repo["name"])
        releases.append(
          {
            "repo": repo["name"],
            "repo_url": repo["url"],
            "description": repo["description"],
            "release": repo["releases"]["nodes"][0]["name"].replace(repo["name"], "").strip(),
            "published_at": repo["releases"]["nodes"][0]["publishedAt"],
            "published_day": repo["releases"]["nodes"][0]["publishedAt"].split("T")[0],
            "url": repo["releases"]["nodes"][0]["url"],
          }
        )
    has_next_page = data["data"]["viewer"]["repositories"]["pageInfo"]["hasNextPage"]
    after_cursor = data["data"]["viewer"]["repositories"]["pageInfo"]["endCursor"]
  return releases


def fetch_tils():
  url = "https://raw.githubusercontent.com/santiagoballadares/til/master/entries.json"
  res = httpx.get(url)
  return res.json()


if __name__ == "__main__":
  readme_md = root / "README.md"
  releases_md = root / "releases.md"

  all_releases = fetch_releases(WORKFLOW_TOKEN)
  all_releases.sort(key=lambda r: r["published_at"], reverse=True)

  # Update README.md file
  readme_releases = "\n".join(
    [
      "* [{repo} {release}]({url}) - {published_day}".format(**release)
      for release in all_releases[:10]
    ]
  )
  readme_md_content = readme_md.open().read()
  rewritten_readme_md = replace_chunk(readme_md_content, "releases", readme_releases)

  last_tils = fetch_tils()[::-1][:5]
  readme_tils = "\n".join(
    [
        "* [{title}]({url}) - {created}".format(title=til["title"], url=til["url"], created=til["created"].split("T")[0])
        for til in last_tils
    ]
  )
  rewritten_readme_md = replace_chunk(rewritten_readme_md, "tils", readme_tils)

  readme_md.open("w").write(rewritten_readme_md)

  # Update releases.md file
  releases = "\n".join(
    [
      (
        "* **[{repo}]({repo_url})**: [{release}]({url}) - {published_day}\n"
        "<br>{description}"
      ).format(**release)
      for release in all_releases
    ]
  )
  releases_md_content = releases_md.open().read()
  rewritten_releases_md = replace_chunk(releases_md_content, "releases", releases)
  rewritten_releases_md = replace_chunk(rewritten_releases_md, "releases_count", str(len(all_releases)), inline=True)
  releases_md.open("w").write(rewritten_releases_md)