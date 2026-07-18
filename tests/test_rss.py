"""Unit tests for RSS parsing (no network)."""

from freakonomics_dl.rss import parse_rss_feed, display_title
from freakonomics_dl.rss_downloader import rss_basename as dl_basename


SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
  <channel>
    <title>Test Podcast</title>
    <item>
      <title>58. What's So Gratifying About Gossip?</title>
      <guid isPermaLink="false">guid-58</guid>
      <itunes:episode>58</itunes:episode>
      <enclosure url="https://example.com/ep58.mp3" length="12345" type="audio/mpeg"/>
      <description>&lt;p&gt;Show notes here.&lt;/p&gt;</description>
      <pubDate>Mon, 01 Jan 2024 12:00:00 GMT</pubDate>
      <itunes:duration>3600</itunes:duration>
      <link>https://example.com/ep58</link>
    </item>
    <item>
      <title>Untitled Bonus</title>
      <guid>guid-bonus</guid>
      <enclosure url="https://example.com/bonus.mp3" type="audio/mpeg"/>
    </item>
    <item>
      <title>No Audio Item</title>
      <guid>guid-na</guid>
      <description>Text only</description>
    </item>
  </channel>
</rss>
"""


def test_parse_rss_counts_and_fields():
    eps = parse_rss_feed(SAMPLE_RSS)
    assert len(eps) == 3
    first = eps[0]
    assert first.episode_num == 58
    assert first.audio_url == "https://example.com/ep58.mp3"
    assert first.audio_length == 12345
    assert first.guid == "guid-58"
    assert "Show notes" in first.description
    assert eps[1].episode_num is None
    assert eps[2].audio_url is None


def test_basename_with_episode_number():
    eps = parse_rss_feed(SAMPLE_RSS)
    assert dl_basename(eps[0]).startswith("58-")
    assert "Gossip" in dl_basename(eps[0])
    assert not dl_basename(eps[1])[0].isdigit() or "-" not in dl_basename(eps[1])[:3]


def test_display_title_strips_numeric_prefix():
    eps = parse_rss_feed(SAMPLE_RSS)
    assert not display_title(eps[0]).startswith("58.")
