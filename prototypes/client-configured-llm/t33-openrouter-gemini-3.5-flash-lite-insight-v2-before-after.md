# Revised summary prompt and deterministic output contract — before/after review

**PROTOTYPE — model text is shown untruncated and unmodified.**

Measured 15/16 available non-holdout references. This review shows every case that failed the prior prompt's measured quantity or 25-word checks.

## 3m-acquired-jamie-dimon

**Prior failures:** {"summaryWordCount":30,"summaryAtMost25Words":false,"topicCount":2,"topicCountInDefaultRange":true,"detailCount":5,"missingDetailTimestamps":0,"invalidDetailTimestamps":0,"sourceDigitTokenCount":4,"outputDataReferenceDigitTokenCount":3,"missingSourceDigitTokens":["2"],"unsupportedOutputDigitTokens":[],"unsupportedBackgroundNames":[],"broaderSemanticFactualDefects":"unmeasured","spelledNumberCoverage":"unmeasured"}

### Before — unchanged reference prompt

```json
{
  "summary": "Ben introduces Jamie Dimon as the stabilizer of the US financial system and leader of the largest US bank, setting the stage for a live interview exploring his unique success.",
  "topics": [
    {
      "title": "Jamie Dimon's Leadership and JPMorgan's Dominance",
      "description": "Ben describes Jamie Dimon as the longest-serving CEO of a major Wall Street bank and the stabilizer of the American financial system during the 2008 crisis. He highlights JPMorgan's status as the largest US bank with a market cap over $800 billion, making it the most valuable company east of the Mississippi."
    },
    {
      "title": "Live Event Format and Context",
      "description": "Ben explains that the episode was recorded live in front of 6,000 fans at Radio City Music Hall, marking a different format for the Acquired podcast. He notes the event included a second act with other CEOs and thanked J.P. Morgan as the presenting partner."
    }
  ],
  "details": [
    {
      "title": "Dimon's Role and Bank Size",
      "description": "Ben states that Jamie Dimon is the longest-serving CEO of a major Wall Street bank and is viewed as the great stabilizer of the American financial system, particularly during the 2008 crisis. He notes JPMorgan has an over $800 billion market cap, more than twice its nearest competitor.",
      "timestamp": "00:00:01"
    },
    {
      "title": "Geographic Financial Superiority",
      "description": "Ben emphasizes that JPMorgan is the most valuable company east of the Mississippi and the only one there worth more than half a trillion dollars.",
      "timestamp": "00:00:28"
    },
    {
      "title": "Questioning Dimon's Strategy",
      "description": "Ben asks how Dimon achieved this success, contrasting it with the common failures and organizational bloat seen in other large financial firms.",
      "timestamp": "00:00:41"
    },
    {
      "title": "Live Event Details",
      "description": "Ben reveals the episode was recorded live in front of 6,000 Acquired fans at Radio City Music Hall in New York City, featuring a different format with a second act involving other CEOs.",
      "timestamp": "00:00:58"
    },
    {
      "title": "Sponsorship and Disclaimers",
      "description": "Ben thanks J.P. Morgan as the presenting partner and notes their payments team demonstrated technology at the event, followed by standard non-investment advice disclaimers.",
      "timestamp": "00:01:36"
    }
  ],
  "data_references": [
    {
      "item": "Market capitalization",
      "value": "over $800 billion",
      "context": "JPMorgan's market cap is more than twice their nearest competitor"
    },
    {
      "item": "Valuation threshold",
      "value": "half a trillion dollars",
      "context": "JPMorgan is the only company east of the Mississippi worth more than this amount"
    },
    {
      "item": "Crisis year",
      "value": "2008",
      "context": "The financial crisis during which Dimon stabilized the system"
    },
    {
      "item": "Audience size",
      "value": "6000",
      "context": "Number of Acquired fans present at the Radio City Music Hall recording"
    },
    {
      "item": "Event duration context",
      "value": "almost a year ago",
      "context": "Time since Ben and David started planning the show"
    }
  ],
  "speaker_background": [
    "Ben: Host of Acquired podcast",
    "David: Co-host of Acquired podcast",
    "Jamie Dimon: CEO of J.P. Morgan and longest-serving CEO of any major Wall Street bank"
  ]
}
```

### After — revised prompt alone

Attempts: 1; latency: 1944 ms; deterministic contract passed: true.

```json
{
  "summary": "Jamie Dimon has led JPMorgan Chase to become the largest and most dominant bank in the United States, commanding a market cap exceeding $800 billion and standing as the only company east of the Mississippi worth over half a trillion dollars. In a live interview at Radio City Music Hall, hosts Ben and David explore how JPMorgan avoided the specter of spectacular blowups and bloat that historically plagues financial institutions.",
  "topics": [
    {
      "title": "JPMorgan Chase's Unprecedented Scale and Dominance",
      "description": "JPMorgan Chase operates with an over $800 billion market cap, more than double its nearest competitor, making it the most valuable company east of the Mississippi and the only financial institution in striking distance of major tech giants."
    }
  ],
  "details": [
    {
      "title": "Introduction of Jamie Dimon and Bank Dominance",
      "description": "Ben introduces Jamie Dimon as the longest-serving CEO of a major Wall Street bank and the stabilizing force of the American financial system, highlighting JPMorgan's massive market capitalization and unique geographic status.",
      "timestamp": "00:00:01"
    }
  ],
  "speaker_background": [],
  "data_references": [
    {
      "item": "JPMorgan market cap",
      "value": "over $800 billion",
      "context": "Illustrates the immense scale of JPMorgan, making it more than twice the size of its nearest competitor and a rare financial titan rivaling big tech."
    }
  ]
}
```

### After — revised prompt with exact contract feedback

Attempts: 1; latency: 1624 ms; deterministic contract passed: true.

```json
{
  "summary": "Jamie Dimon leads JPMorgan Chase, the largest bank in the U.S. with a market cap exceeding $800 billion, making it the only company east of the Mississippi worth more than half a trillion dollars. This briefing covers the introductory context of his long tenure, banking dominance, and the live podcast format used at Radio City Music Hall in New York City.",
  "topics": [
    {
      "title": "JPMorgan Chase's Market Dominance",
      "description": "JPMorgan Chase operates with an over $800 billion market cap—more than twice its nearest competitor—and stands as the most valuable company east of the Mississippi River in the United States."
    }
  ],
  "details": [
    {
      "title": "Live Show Context and Format",
      "description": "The episode was recorded live in front of 6,000 fans at Radio City Music Hall featuring a new live format, with a second act planned as a late-night talk show.",
      "timestamp": "00:00:58"
    }
  ],
  "speaker_background": [],
  "data_references": [
    {
      "item": "JPMorgan Chase market capitalization",
      "value": "over $800 billion",
      "context": "Highlights the massive scale of the bank under Jamie Dimon, making it more than twice its nearest competitor."
    }
  ]
}
```

## 5m-acquired-nfl

**Prior failures:** {"summaryWordCount":26,"summaryAtMost25Words":false,"topicCount":2,"topicCountInDefaultRange":true,"detailCount":6,"missingDetailTimestamps":0,"invalidDetailTimestamps":0,"sourceDigitTokenCount":2,"outputDataReferenceDigitTokenCount":2,"missingSourceDigitTokens":[],"unsupportedOutputDigitTokens":[],"unsupportedBackgroundNames":[],"broaderSemanticFactualDefects":"unmeasured","spelledNumberCoverage":"unmeasured"}

### Before — unchanged reference prompt

```json
{
  "summary": "Ben Gilbert and David Rosenthal introduce a remastered NFL episode, highlighting the league's growth, the Taylor Swift crossover, and their upcoming 2026 Super Bowl Innovation Summit.",
  "topics": [
    {
      "title": "Remastered Episode Context and Updates",
      "description": "Ben Gilbert introduces the remastered edition of their January 2023 NFL episode, noting that the league has become an even larger juggernaut since then. David Rosenthal agrees that the original episode is essential to their canon and adds that they are hosting the Super Bowl's Innovation Summit in San Francisco in 2026."
    },
    {
      "title": "NFL Popularity and Business Model",
      "description": "Ben Gilbert states that football is America's favorite sport, being more than three times as popular as basketball. He explains that the NFL became the most valuable media property through cooperation and equal revenue division among owners."
    }
  ],
  "details": [
    {
      "title": "Fox Sports Theme Nostalgia",
      "description": "Ben Gilbert mentions growing up listening to the Fox Sports football theme, while David Rosenthal associates it with Thanksgiving.",
      "timestamp": "00:00:02"
    },
    {
      "title": "Remastered NFL Episode Introduction",
      "description": "Ben Gilbert introduces the remastered Acquired episode on the NFL, referencing their original January 2023 release and its importance to their content canon.",
      "timestamp": "00:00:42"
    },
    {
      "title": "Post-2023 NFL Developments",
      "description": "Ben Gilbert lists three changes since the original episode: the NFL's increased dominance, Acquired's audience growth, and the NFL-Taylor Swift crossover.",
      "timestamp": "00:01:05"
    },
    {
      "title": "Super Bowl Innovation Summit Announcement",
      "description": "David Rosenthal corrects Ben by adding that they will host the Super Bowl's Innovation Summit in San Francisco in 2026.",
      "timestamp": "00:01:37"
    },
    {
      "title": "Private Equity Segment Tease",
      "description": "David Rosenthal teases a wild story about how private equity has entered the league, which will be included in a new section at the end of the episode.",
      "timestamp": "00:02:24"
    },
    {
      "title": "NFL Popularity and Revenue Model",
      "description": "Ben Gilbert states that football is more than three times as popular as basketball and became the most valuable media property through equal revenue division among owners.",
      "timestamp": "00:02:48"
    }
  ],
  "data_references": [
    {
      "item": "Time since original episode release",
      "value": "Three years",
      "context": "Ben mentions the time elapsed since the original NFL episode was released."
    },
    {
      "item": "Original episode release date",
      "value": "January of 2023",
      "context": "Ben specifies when the original NFL episode was released."
    },
    {
      "item": "Super Bowl Innovation Summit year",
      "value": "2026",
      "context": "David states the year they are hosting the summit."
    },
    {
      "item": "Super Bowl Innovation Summit location",
      "value": "San Francisco",
      "context": "David specifies the location of the upcoming summit."
    },
    {
      "item": "Football popularity multiplier",
      "value": "more than three times",
      "context": "Ben states football is more than three times as popular as the next highest sport, basketball."
    }
  ],
  "speaker_background": [
    "Ben Gilbert: Host of Acquired podcast",
    "David Rosenthal: Host of Acquired podcast"
  ]
}
```

### After — revised prompt alone

Attempts: 1; latency: 2762 ms; deterministic contract passed: true.

```json
{
  "summary": "This briefing examines the remastered Acquired episode on the National Football League, highlighting how it became America's dominant sports and media property. Driven by a century of strategic cooperation, equal revenue sharing among owners, and recent juggernaut-level growth—including the Taylor Swift crossover and private equity entry—the NFL stands as a masterclass in growing the collective pie.",
  "topics": [
    {
      "title": "Cooperation and Equal Revenue Sharing as a Growth Engine",
      "description": "Unlike other sports leagues, NFL owners have historically chosen to divide their revenues equally. Ben Gilbert likens this to 'communist capitalism at its finest,' explaining that bold, long-term bets on sharing revenues enabled unprecedented collective growth and made the NFL America's most valuable media property."
    },
    {
      "title": "Modern Expansion and New Crossovers",
      "description": "In this 2026 remastered edition, the hosts note that the NFL has grown even further since their 2023 episode, propelled by audience expansion, the cultural phenomenon of the Taylor Swift-NFL crossover, and the recent entry of private equity into the league."
    }
  ],
  "details": [
    {
      "title": "Remastering the NFL Episode for 2026",
      "description": "Ben Gilbert and David Rosenthal explain that they are remastering their January 2023 NFL episode to current production standards in anticipation of hosting the Super Bowl's Innovation Summit in San Francisco in 2026.",
      "timestamp": "00:00:53"
    },
    {
      "title": "Private Equity Enters the NFL",
      "description": "David Rosenthal teases a wild and nuts new section at the end of the episode detailing how private equity has officially entered the National Football League.",
      "timestamp": "00:02:24"
    },
    {
      "title": "The Core Philosophy of the NFL",
      "description": "Ben Gilbert outlines that the NFL's dominance is built on incredible cooperation and a century-long belief in growing the pie together through equal revenue sharing among owners.",
      "timestamp": "00:03:44"
    }
  ],
  "speaker_background": [
    "Ben Gilbert: Co-host of Acquired",
    "David Rosenthal: Co-host of Acquired"
  ],
  "data_references": [
    {
      "item": "Relative popularity of football compared to basketball",
      "value": "More than three times as popular",
      "context": "Demonstrates the massive scale of football's dominance over America's next highest sport."
    }
  ]
}
```

### After — revised prompt with exact contract feedback

Attempts: 1; latency: 2210 ms; deterministic contract passed: true.

```json
{
  "summary": "This briefing covers a remastered and updated episode on the National Football League, highlighting how it became America's dominant sports and media property. Driven by a century of revenue sharing, long-term bets, and unprecedented growth, the league has evolved into a juggernaut that recently incorporated private equity and massive cultural crossovers.",
  "topics": [
    {
      "title": "The Power of Equal Revenue Sharing",
      "description": "Unlike other sports leagues, NFL owners have historically chosen to divide revenues equally. This commitment to growing the pie and cooperative long-term bets is likened to 'communist capitalism at its finest' and underpins the league's massive success."
    },
    {
      "title": "Modern Juggernaut and Crossovers",
      "description": "The NFL has expanded its cultural footprint significantly through major events like hosting the Super Bowl Innovation Summit, integrating the Taylor Swift phenomenon, and opening the door to private equity ownership."
    }
  ],
  "details": [
    {
      "title": "NFL's Popularity Relative to Other Sports",
      "description": "Ben Gilbert notes that football is America's favorite sport by far, specifically being more than three times as popular as basketball, the next highest sport.",
      "timestamp": "00:02:48"
    },
    {
      "title": "Private Equity Entry",
      "description": "David Rosenthal highlights that private equity has entered the league, describing the story as 'nuts' and teasing a special new section at the end of the remastered episode.",
      "timestamp": "00:02:24"
    }
  ],
  "speaker_background": [],
  "data_references": [
    {
      "item": "Football's relative popularity multiplier compared to the next highest sport",
      "value": "more than three times",
      "context": "Highlights the sheer dominance of football as America's favorite sport by far."
    }
  ]
}
```

## 5m-lex-bill-ackman

**Prior failures:** {"summaryWordCount":29,"summaryAtMost25Words":false,"topicCount":3,"topicCountInDefaultRange":true,"detailCount":10,"missingDetailTimestamps":0,"invalidDetailTimestamps":0,"sourceDigitTokenCount":1,"outputDataReferenceDigitTokenCount":1,"missingSourceDigitTokens":[],"unsupportedOutputDigitTokens":[],"unsupportedBackgroundNames":[],"broaderSemanticFactualDefects":"unmeasured","spelledNumberCoverage":"unmeasured"}

### Before — unchanged reference prompt

```json
{
  "summary": "Bill Ackman explains that Benjamin Graham's 'The Intelligent Investor' taught him to distinguish price from value, viewing the market as a servant that aids long-term investing over short-term speculation.",
  "topics": [
    {
      "title": "Price vs. Value and Market Mechanics",
      "description": "Bill Ackman identifies Benjamin Graham's 'The Intelligent Investor' as the foundational text for his career, emphasizing the core lesson that price is what you pay while value is what you get. He uses the analogy of a neighbor making daily offers on a house to illustrate that the stock market exists to serve the investor, not dictate their actions."
    },
    {
      "title": "Speculation vs. Investing and Valuation",
      "description": "Ackman distinguishes investing from speculation by defining the value of any asset as the present value of cash extractable over its life. He contrasts short-term trading, which he likens to crypto speculation, with deep fundamental analysis of business competitive dynamics and management."
    },
    {
      "title": "Predictability of Cash Flows",
      "description": "Ackman argues that true investing requires finding rare companies where future cash flows can be predicted with high confidence over long periods. He compares stocks to bonds, noting that while bonds have contractual certainty, stocks require predicting sales, costs, and reinvestment needs."
    }
  ],
  "details": [
    {
      "title": "Opening Statement on Journalists",
      "description": "Bill Ackman opens the conversation by stating that a journalist with a pen can cause more harm than a thief with a dagger.",
      "timestamp": "00:00:00"
    },
    {
      "title": "Introduction of Bill Ackman",
      "description": "Lex Fridman introduces Bill Ackman as a legendary activist investor known for controversial trades and vocal activism on X, including his role in the resignation of Harvard President Claudine Gay.",
      "timestamp": "00:00:06"
    },
    {
      "title": "Impact of Intelligent Investor",
      "description": "Bill Ackman states that 'The Intelligent Investor' was the first investment book he read and served as the primary inspiration for his career and life choices.",
      "timestamp": "00:01:00"
    },
    {
      "title": "Price Versus Value Distinction",
      "description": "Ackman explains Graham's key lesson that investors must understand the difference between price and value, noting the book was written after the Great Depression and World War II to restore market confidence.",
      "timestamp": "00:01:15"
    },
    {
      "title": "Stock Market as Servant",
      "description": "Ackman describes the stock market as a service provider that makes daily offers, using the analogy of a neighbor offering to buy a house to explain how investors should evaluate market prices.",
      "timestamp": "00:01:30"
    },
    {
      "title": "Voting Machine vs Weighing Machine",
      "description": "Ackman quotes Graham's distinction that the stock market is a voting machine in the short term due to speculation, but a weighing machine in the long term that accurately reflects value.",
      "timestamp": "00:01:44"
    },
    {
      "title": "Speculation Defined as Short-Term Trading",
      "description": "Bill Ackman defines speculation as short-term trading, comparing it to crypto, where investors buy assets simply because prices are rising without knowing their intrinsic worth.",
      "timestamp": "00:02:18"
    },
    {
      "title": "Investing Defined as Homework",
      "description": "Ackman defines investing as doing homework to understand a business, its industry dynamics, and management, asserting that value is the present value of cash extractable over the asset's life.",
      "timestamp": "00:02:27"
    },
    {
      "title": "Valuing Bonds and Stocks",
      "description": "Ackman explains that bonds are easy to value due to predictable coupons, whereas stocks require predicting future sales, costs, and reinvestment needs, making them more complex to value.",
      "timestamp": "00:03:35"
    },
    {
      "title": "Finding Predictable Businesses",
      "description": "Ackman states that his professional focus is finding rare companies where future cash flows can be predicted with high confidence over a very long period.",
      "timestamp": "00:04:22"
    }
  ],
  "data_references": [
    {
      "item": "Coupon rate of bond example",
      "value": "5%",
      "context": "Ackman uses a bond paying a 5% coupon to illustrate predictable cash flows"
    },
    {
      "item": "Frequency of bond payments",
      "value": "every year or twice a year",
      "context": "Ackman describes how bond coupons are typically paid out"
    }
  ],
  "speaker_background": [
    "Bill Ackman: legendary activist investor",
    "Lex Fridman: host of the Lex Fridman podcast"
  ]
}
```

### After — revised prompt alone

Attempts: 1; latency: 2363 ms; deterministic contract passed: true.

```json
{
  "summary": "Bill Ackman outlines foundational value investing principles learned from Benjamin Graham's 'The Intelligent Investor,' emphasizing the distinction between short-term market price and long-term intrinsic value. He defines the value of a stock as the present value of the cash flows a business can produce over its lifetime, contrasting rigorous business analysis against speculative trading.",
  "topics": [
    {
      "title": "Price versus Value and the Market Metaphor",
      "description": "Benjamin Graham's core lesson is that the stock market acts as a daily neighbor offering to buy or sell your house. By ignoring stupid offers and accepting great ones, investors exploit the market rather than letting it dictate their actions."
    },
    {
      "title": "Voting Machine vs. Weighing Machine",
      "description": "In the short term, the stock market functions as a voting machine driven by speculative interest and supply and demand. In the long term, it acts as a weighing machine that accurately reflects a company's true worth."
    },
    {
      "title": "Investing versus Speculation",
      "description": "Speculation relies on assets going up without knowing their intrinsic value, akin to short-term crypto trading. True investing requires rigorous homework, analyzing competitive dynamics, management capabilities, and cash flows."
    },
    {
      "title": "Valuing Stocks Like Bonds",
      "description": "A stock represents an interest in a business much like a bond, where value equals the present value of future cash flows. While bonds have contractual certainty, stocks require predicting future business performance, costs, and reinvestment needs."
    }
  ],
  "details": [
    {
      "title": "Benjamin Graham's Influence",
      "description": "Bill Ackman notes that 'The Intelligent Investor' was the first investment book he read after the post-Great Depression and World War II era, serving as the primary inspiration for his career.",
      "timestamp": "00:00:47"
    },
    {
      "title": "Definition of Intrinsic Value",
      "description": "Ackman defines the value of anything other than love as the present value of the cash you can take out of it over its life.",
      "timestamp": "00:02:27"
    }
  ],
  "speaker_background": [
    "Bill Ackman: Legendary activist investor"
  ],
  "data_references": []
}
```

### After — revised prompt with exact contract feedback

Attempts: 1; latency: 2537 ms; deterministic contract passed: true.

```json
{
  "summary": "Bill Ackman outlines foundational value investing principles drawn from Benjamin Graham's 'The Intelligent Investor,' contrasting short-term market speculation with long-term fundamental analysis. He explains that a security's intrinsic value is determined by the present value of its future cash flows, likening stocks to variable bonds that require rigorous business forecasting rather than contract guarantees.",
  "topics": [
    {
      "title": "Price versus Value and the Market as a Servant",
      "description": "Drawing from Benjamin Graham, Ackman emphasizes that market price and intrinsic value are distinct. The stock market acts like a neighbor making frequent purchase offers; investors should ignore foolish offers and capitalize on great ones, leveraging the market rather than letting it dictate decisions."
    },
    {
      "title": "The Voting Machine Versus the Weighing Machine",
      "description": "In the short term, the stock market functions as a voting machine driven by speculative supply, demand, and sentiment. In the long term, it acts as a weighing machine that accurately reflects underlying economic value."
    },
    {
      "title": "Investing Versus Speculation",
      "description": "Speculation involves buying assets simply because their prices are rising without understanding intrinsic worth, akin to short-term crypto trading. True investing requires rigorous homework, competitive analysis, and calculating the present value of cash flows generated over a business's lifetime."
    }
  ],
  "details": [
    {
      "title": "Benjamin Graham's formative impact",
      "description": "Bill Ackman discusses how reading 'The Intelligent Investor' after the post-World War II period shaped his career by introducing core concepts like the difference between price and value.",
      "timestamp": "00:00:47"
    },
    {
      "title": "Defining the intrinsic value of a security",
      "description": "Ackman defines the value of any non-love asset as the present value of the cash that can be extracted from it over its life, comparing a stock's earnings power to a bond's predictable coupon payments.",
      "timestamp": "00:03:35"
    }
  ],
  "speaker_background": [
    "Bill Ackman: Legendary activist investor",
    "Lex Fridman: Podcast host"
  ],
  "data_references": [
    {
      "item": "Bond coupon interest rate used as an illustrative example",
      "value": "5%",
      "context": "Used to explain the predictable, contractual nature of bond yields compared to the variable cash flows of a stock."
    }
  ]
}
```

## 30m-lex-bill-ackman

**Prior failures:** {"summaryWordCount":25,"summaryAtMost25Words":true,"topicCount":4,"topicCountInDefaultRange":true,"detailCount":11,"missingDetailTimestamps":0,"invalidDetailTimestamps":0,"sourceDigitTokenCount":22,"outputDataReferenceDigitTokenCount":19,"missingSourceDigitTokens":["$1","18","19","2"],"unsupportedOutputDigitTokens":["100"],"unsupportedBackgroundNames":[],"broaderSemanticFactualDefects":"unmeasured","spelledNumberCoverage":"unmeasured"}

### Before — unchanged reference prompt

```json
{
  "summary": "Bill Ackman explains value investing principles, emphasizing intrinsic value and margin of safety, while analyzing the enduring moats of Universal Music Group, Chipotle, and Alphabet.",
  "topics": [
    {
      "title": "Value Investing Principles",
      "description": "Bill Ackman cites Benjamin Graham's 'The Intelligent Investor' as foundational, defining value as the present value of future cash flows. He distinguishes investing from speculation by emphasizing the need to understand business fundamentals and competitive dynamics rather than relying on short-term market sentiment."
    },
    {
      "title": "Universal Music Group Strategy",
      "description": "Ackman describes Universal Music Group as a non-disruptive business with high persistence due to its dominant market share and iconic catalog. He argues that streaming provides predictable revenue models and that AI will likely serve as a tool for artists rather than replacing the human connection fans seek."
    },
    {
      "title": "Restaurant Industry Moats",
      "description": "Ackman identifies businesses like Chipotle and McDonald's as examples of companies with durable moats built on systems and brand loyalty. He notes that while food safety issues can create buying opportunities, the underlying demand for consistent, scalable food models remains strong."
    },
    {
      "title": "Alphabet Valuation and AI",
      "description": "Ackman argues that Alphabet is undervalued due to an overreaction to AI competition, citing its dominant search moat and massive data advantages. He highlights the company's low earnings multiple and strong cash position as attractive features for long-term investors."
    }
  ],
  "details": [
    {
      "title": "Intelligent Investor Lesson",
      "description": "Bill Ackman states that Benjamin Graham's book taught him to distinguish between price and value, viewing the market as a service that offers opportunities to buy low and sell high.",
      "timestamp": "00:01:00"
    },
    {
      "title": "Speculation vs Investing",
      "description": "Ackman defines speculation as trading based on price movements without understanding intrinsic value, whereas investing involves modeling a business's lifetime cash flows and understanding its competitive landscape.",
      "timestamp": "00:02:18"
    },
    {
      "title": "Valuing Securities",
      "description": "Ackman explains that a security's value is the present value of cash extractable over its life, comparing stocks to bonds that generate variable coupons based on business performance.",
      "timestamp": "00:03:35"
    },
    {
      "title": "Universal Music Group Strategy",
      "description": "Ackman highlights Universal Music Group's dominance in recorded music and publishing, noting that streaming offers predictable growth based on smartphone penetration and subscription models.",
      "timestamp": "00:05:19"
    },
    {
      "title": "Margin of Safety",
      "description": "Ackman emphasizes buying at a deep discount to estimated value to protect against errors, stating that avoiding losses is key to long-term investment success.",
      "timestamp": "00:07:30"
    },
    {
      "title": "Music Industry Evolution",
      "description": "Ackman notes that Universal helped save the industry from Napster by adopting streaming early, leveraging its vast catalog of timeless artists like the Beatles and Rolling Stones.",
      "timestamp": "00:08:43"
    },
    {
      "title": "AI in Music",
      "description": "Ackman agrees with Fridman that AI will likely enhance artists rather than replace them, as fans value the human story and live experience behind the music.",
      "timestamp": "00:10:32"
    },
    {
      "title": "Fast Food Longevity",
      "description": "Ackman cites McDonald's as a stable business with predictable long-term prospects, noting that core items like hamburgers and fries remain relevant despite menu changes.",
      "timestamp": "00:12:56"
    },
    {
      "title": "Chipotle Investment Thesis",
      "description": "Ackman explains that Chipotle's stock dropped significantly due to a food safety issue, but the company's strong brand and difficult-to-replicate fresh food moat made it an attractive investment.",
      "timestamp": "00:14:16"
    },
    {
      "title": "Restaurant Industry Moats",
      "description": "Ackman describes the restaurant business as having a strong track record, with moats built on systems, brand image, and difficult-to-replicate supply chains like Chipotle's fresh ingredients.",
      "timestamp": "00:20:04"
    },
    {
      "title": "Alphabet Valuation and AI",
      "description": "Ackman argues that Alphabet is undervalued due to an overreaction to AI competition, citing its dominant search moat, massive data advantages, and low earnings multiple.",
      "timestamp": "00:24:53"
    }
  ],
  "data_references": [
    {
      "item": "Coupon rate for bond example",
      "value": "5%",
      "context": "Ackman uses a bond paying a 5% coupon to illustrate predictable cash flows."
    },
    {
      "item": "Market share of Universal Music Group",
      "value": "a third",
      "context": "Ackman states UMG owns a third of the global recorded music market."
    },
    {
      "item": "Streaming subscription cost",
      "value": "10, 11 bucks a month",
      "context": "Ackman estimates the monthly cost for a streaming subscription or family plan."
    },
    {
      "item": "Potential value discrepancy",
      "value": "30%",
      "context": "Ackman mentions the margin of safety if the estimated value is 30% less than thought."
    },
    {
      "item": "Peak of music industry",
      "value": "late '90s or 2000",
      "context": "Ackman notes the music business peaked in the late '90s or 2000 timeframe."
    },
    {
      "item": "Age of McDonald's business model",
      "value": "1950 vintage",
      "context": "Ackman describes McDonald's as an 1950 vintage business."
    },
    {
      "item": "Time elapsed for McDonald's",
      "value": "75 years",
      "context": "Ackman notes it has been 75 years since the 1950s."
    },
    {
      "item": "Chipotle stock price drop",
      "value": "about 50%",
      "context": "Ackman notes Chipotle's stock price dropped by about 50% due to a food safety issue."
    },
    {
      "item": "Chipotle store growth potential",
      "value": "100 stores to 200 stores to 500 stores",
      "context": "Ackman uses this progression to illustrate the ease of envisioning growth for a restaurant business."
    },
    {
      "item": "Chipotle store count complexity",
      "value": "3,500 stores",
      "context": "Ackman notes that scaling to 3,500 stores introduces significant complexity."
    },
    {
      "item": "Burger patty price",
      "value": "$1.50 or $2",
      "context": "Lex Fridman mentions the price of a burger patty at McDonald's or Burger King."
    },
    {
      "item": "Burger patty calories",
      "value": "250 calories",
      "context": "Lex Fridman states a burger patty is about 250 calories."
    },
    {
      "item": "Alphabet earnings multiple",
      "value": "15 times earnings",
      "context": "Ackman notes Google's stock got to a price around 15 times earnings."
    },
    {
      "item": "Alphabet earnings yield",
      "value": "almost a seven and a half percent yield",
      "context": "Ackman calculates the yield based on the 15 multiple."
    },
    {
      "item": "Government lending rate",
      "value": "4%",
      "context": "Ackman compares the earnings yield to what you can earn lending money to the government."
    },
    {
      "item": "Alphabet cloud investment",
      "value": "hundred percent",
      "context": "Ackman states Google invests basically a hundred percent of its cloud profits into growth."
    },
    {
      "item": "Alphabet admiration period",
      "value": "15 years",
      "context": "Ackman says the firm has admired Alphabet as a business for 15 years."
    },
    {
      "item": "Conference call history review",
      "value": "five years",
      "context": "Ackman suggests going back five years in conference call transcripts to learn the story."
    },
    {
      "item": "Chipotle dinner cost",
      "value": "under 20 bucks",
      "context": "Ackman notes you can get a serious dinner for under 20 bucks at Chipotle."
    },
    {
      "item": "Burger King franchise brands",
      "value": "Burger King, McDonald's, Tim Horton's, Popeyes",
      "context": "Ackman lists these brands as examples of successful franchise models."
    },
    {
      "item": "Post March 2020 tech growth",
      "value": "March '20",
      "context": "Ackman references the post March '20 world where tech companies grew enormously."
    }
  ],
  "speaker_background": [
    "Bill Ackman: legendary activist investor",
    "Lex Fridman: host of the Lex Fridman podcast"
  ]
}
```

### After — revised prompt alone

Attempts: 1; latency: 3480 ms; deterministic contract passed: true.

```json
{
  "summary": "Legendary activist investor Bill Ackman outlines his core investment philosophy, emphasizing Benjamin Graham's distinction between price and value, the necessity of a margin of safety, and the importance of investing in non-disruptive businesses with long-term predictability. Using examples like Universal Music Group, Chipotle, and Alphabet, he explains how market overreactions to temporary crises or paradigm shifts create opportunities to acquire dominant franchises at a discount.",
  "topics": [
    {
      "title": "Price vs. Value and the Margin of Safety",
      "description": "Benjamin Graham's foundational insight is that the stock market acts as a voting machine in the short term and a weighing machine in the long term. Ackman explains that successful investing requires determining the present value of a business's lifetime cash flows and purchasing at a significant discount—a margin of safety—to protect against forecasting errors."
    },
    {
      "title": "Moats and Predictability in a Disruptive Era",
      "description": "Navigating the modern era of rapid technological disruption requires identifying businesses with massive barriers to entry and enduring consumer demand. Ackman uses examples like music, fast food, and search to illustrate that while form factors and technologies change, foundational human desires and deeply integrated distribution systems persist."
    },
    {
      "title": "Market Overreaction and Contrarian Investing",
      "description": "Because great businesses naturally command high stock prices, Ackman seeks out opportunities where high-quality companies have stumbled due to temporary operational missteps, crises, or fear of technological shifts (such as Alphabet's initial AI scare), allowing him to buy cash-generative dominant enterprises at low earnings multiples."
    }
  ],
  "details": [
    {
      "title": "The definition of investing versus speculation",
      "description": "Ackman defines investing as building a rigorous model of a business's lifetime cash flows based on fundamentals, whereas short-term trading without knowing intrinsic value is pure speculation.",
      "timestamp": "00:02:18"
    },
    {
      "title": "Universal Music Group's streaming moat",
      "description": "UMG possesses a dominant market share in recorded music and publishing, benefiting from timeless content like the Beatles and predictable global smartphone and streaming penetration.",
      "timestamp": "00:05:19"
    },
    {
      "title": "Chipotle's recovery and business model",
      "description": "Chipotle survived a food safety crisis because its core fresh, high-quality, sustainably sourced food concept remains extraordinarily difficult to replicate, forming a durable economic moat.",
      "timestamp": "00:14:16"
    },
    {
      "title": "Alphabet's overreaction and earnings yield",
      "description": "When Microsoft released ChatGPT and Google's early Bard demonstration stumbled, the market panicked, driving Google down to a 15 times earnings multiple (nearly a 7.5% earnings yield). Ackman argues the market overlooked Google's superior data assets, massive engineering talent, and financial strength.",
      "timestamp": "00:24:13"
    }
  ],
  "speaker_background": [
    "Bill Ackman: legendary activist investor",
    "Lex Fridman: podcast host"
  ],
  "data_references": [
    {
      "item": "Alphabet earnings multiple and yield",
      "value": "15 times earnings (~7.5% yield)",
      "context": "Represents the depressed valuation Google reached during the market's AI scare, which offered an attractive going-in yield compared to 4% government bonds."
    }
  ]
}
```

### After — revised prompt with exact contract feedback

Attempts: 1; latency: 4195 ms; deterministic contract passed: true.

```json
{
  "summary": "Bill Ackman outlines his core investment philosophy, emphasizing Benjamin Graham's distinction between price and value, the importance of a margin of safety, and the necessity of identifying non-disruptive businesses with long-term predictability. Using examples like Universal Music Group, Chipotle, and Alphabet, he explains how market overreactions to temporary crises or paradigm shifts create opportunities to acquire dominant franchises at a discount.",
  "topics": [
    {
      "title": "Price versus Value and the Margin of Safety",
      "description": "Investing requires determining the present value of the cash a business will generate over its lifetime. Because predictions are inherently uncertain, investors must demand a margin of safety by purchasing at a deep discount to estimated value, ensuring that even if calculations are flawed by 30%, the investment remains protected."
    },
    {
      "title": "Identifying Moats and Non-Disruptable Businesses",
      "description": "Ackman prioritizes companies with deep barriers to entry and long-term persistence that can withstand technological and market shifts. In quick-service restaurants and music, this durability stems from proprietary operational systems, brand equity, global market share, and irreplaceable content libraries."
    },
    {
      "title": "Capitalizing on Market Overreactions",
      "description": "Dominant, high-quality businesses rarely trade cheaply unless they suffer a temporary crisis or a narrative shock. Ackman illustrates this with Chipotle's food safety issues and Alphabet's initial AI fears, where market panics compressed valuations to attractive earnings yields for companies with massive data, engineering talent, and financial resources."
    }
  ],
  "details": [
    {
      "title": "Benjamin Graham's Market Metaphor",
      "description": "Drawing from Benjamin Graham's 'Intelligent Investor', Ackman describes the stock market as a neighbor who makes daily offers for your house; short term, the market is a voting machine reflecting speculative supply and demand, but long term, it is a weighing machine that accurately reveals intrinsic value.",
      "timestamp": "00:01:00"
    },
    {
      "title": "Universal Music Group's Industry Dominance",
      "description": "Ackman explains why Universal Music Group represents a durable business: it owns a third of global recorded music, represents legendary acts like the Beatles and Rolling Stones, and benefits from predictable recurring revenue from global smartphone and streaming penetration.",
      "timestamp": "00:05:19"
    },
    {
      "title": "Chipotle's Operational Turnaround and Moat",
      "description": "Discussing Chipotle, Ackman notes that when the stock dropped 50% following a food safety crisis, the core high-quality concept remained intact. Its moat lies in its complex supply chain of sustainably sourced, fresh ingredients prepared in-store—a difficult model to replicate compared to mass-produced frozen fast food.",
      "timestamp": "00:14:16"
    },
    {
      "title": "Alphabet's AI Scare and Valuation Opportunity",
      "description": "Alphabet became an attractive position when its stock dropped to about 15 times earnings following early fears that Microsoft's ChatGPT and a flawed Bard demonstration left Google behind in AI. Ackman argues that Google's vast training data, financial resources, and dominant search and YouTube franchises make it undervalued.",
      "timestamp": "00:24:15"
    }
  ],
  "speaker_background": [
    "Bill Ackman: legendary activist investor"
  ],
  "data_references": [
    {
      "item": "Alphabet P/E Multiple",
      "value": "15 times earnings",
      "context": "Illustrates the low price valuation of Alphabet during the AI scare, representing an attractive earnings yield."
    },
    {
      "item": "Alphabet Earnings Yield",
      "value": "almost a seven and a half percent yield",
      "context": "The inverse of a 15 P/E multiple, demonstrating a favorable going-in yield compared to 4% government bond rates."
    }
  ]
}
```

## 5m-acquired-alphabet

**Prior failures:** {"summaryWordCount":24,"summaryAtMost25Words":true,"topicCount":3,"topicCountInDefaultRange":true,"detailCount":7,"missingDetailTimestamps":0,"invalidDetailTimestamps":0,"sourceDigitTokenCount":7,"outputDataReferenceDigitTokenCount":5,"missingSourceDigitTokens":["2","2000"],"unsupportedOutputDigitTokens":[],"unsupportedBackgroundNames":[],"broaderSemanticFactualDefects":"unmeasured","spelledNumberCoverage":"unmeasured"}

### Before — unchanged reference prompt

```json
{
  "summary": "The hosts introduce the Acquired podcast's summer 2025 episode on Google, contrasting its search dominance with numerous product failures and its evolution into Alphabet.",
  "topics": [
    {
      "title": "Podcast Introduction and Host Banter",
      "description": "Ben Gilbert and David Rosenthal open the summer 2025 season of Acquired. They engage in lighthearted banter regarding Ben's attire, with David jokingly comparing it to Steve Jobs."
    },
    {
      "title": "Google's Historical Rise and Product Failures",
      "description": "Ben Gilbert outlines Google's late 1990s rise through superior search algorithms and ad models, leading to its 2004 IPO. He contrasts this success with a list of significant product failures like Google+, Wave, and messaging apps."
    },
    {
      "title": "Episode Scope and Business Model Analysis",
      "description": "Ben describes Google's core business as an ad-driven search engine and outlines the episode's focus on its reorganization into Alphabet. David introduces a quote from Silicon Valley to frame the discussion on revenue versus valuation."
    }
  ],
  "details": [
    {
      "title": "Attire Discussion and Jokes",
      "description": "David asks Ben if his black turtleneck is intentional, joking about Steve Jobs. Ben denies it but acknowledges the comparison to a Google episode.",
      "timestamp": "00:00:02"
    },
    {
      "title": "Acquired Podcast Season Launch",
      "description": "Ben Gilbert officially welcomes listeners to the summer 2025 season of Acquired, introducing himself and co-host David Rosenthal.",
      "timestamp": "00:00:40"
    },
    {
      "title": "Google's Historical Rise to IPO",
      "description": "Ben describes how Google built the best search engine in the late 1990s using breakthrough algorithms and commodity hardware, eventually taking the company public in 2004.",
      "timestamp": "00:00:51"
    },
    {
      "title": "Listing of Google Product Failures",
      "description": "Ben lists colossal failures including Google+, Wave, Buzz, and numerous messaging apps launched over the years, as well as Google Glass and hot air balloons.",
      "timestamp": "00:01:43"
    },
    {
      "title": "Episode Scope and Business Model",
      "description": "Ben outlines the episode's focus on Google's reorganization into Alphabet and its core mission to organize the world's information, ending at the dawn of the AI era.",
      "timestamp": "00:02:14"
    },
    {
      "title": "Silicon Valley Quote Introduction",
      "description": "David introduces a quote from the fictional character Russ Hanneman to discuss the difference between revenue and valuation in tech companies.",
      "timestamp": "00:04:00"
    },
    {
      "title": "Google's Revenue Status",
      "description": "Ben notes that Google is a cash-gushing machine, while David clarifies that the issue in the mid-2000s was being viewed as a pure play rather than having revenue problems.",
      "timestamp": "00:04:40"
    }
  ],
  "data_references": [
    {
      "item": "Podcast season",
      "value": "summer 2025",
      "context": "Ben introduces the current season of the Acquired podcast."
    },
    {
      "item": "Time period of Google's rise",
      "value": "late 1990s",
      "context": "Ben states when Google built the best search engine."
    },
    {
      "item": "IPO year",
      "value": "2004",
      "context": "Ben mentions the year Google took the company public."
    },
    {
      "item": "Number of messaging apps (lower estimate)",
      "value": "about half a dozen",
      "context": "Ben estimates the number of messaging apps launched by Google."
    },
    {
      "item": "Number of messaging apps (upper estimate)",
      "value": "maybe a dozen",
      "context": "Ben provides a higher estimate for the number of messaging apps."
    },
    {
      "item": "Years of valuation concern",
      "value": "2004, 2005, 2006",
      "context": "David mentions the period when Google was viewed as a pure play."
    }
  ],
  "speaker_background": [
    "Ben Gilbert: Host of the Acquired podcast",
    "David Rosenthal: Host of the Acquired podcast"
  ]
}
```

### After — revised prompt alone

Attempts: 1; latency: 2428 ms; deterministic contract passed: true.

```json
{
  "summary": "This briefing explores the early foundation and strategic evolution of Google, from its breakthrough search algorithm and cash-gushing ad business to its identity as a prolific innovation factory. It examines how Google balanced core search dominance with ambitious, often failed moonshots, and how the company structured its ventures to manage market perception and strategic purpose.",
  "topics": [
    {
      "title": "Google's Dual Identity as a Cash Machine and Innovation Factory",
      "description": "Google built an exceptionally lucrative business model on search ads, commodity hardware, and a breakthrough search algorithm. However, the company consistently channeled its resources into diverse moonshots and high-profile failures—ranging from messaging apps and Google Glass to hot-air balloons—raising fundamental questions about whether Google is a pure-play search engine, a web-era platform, or an incubator."
    }
  ],
  "details": [
    {
      "title": "Google's Origins and Business Model Breakthrough",
      "description": "In the late 1990s, Google built the internet's best search engine by combining a breakthrough algorithm, low-cost commodity servers, and search ads, enabling them to go public as a cash-gushing business in 2004.",
      "timestamp": "00:00:51"
    },
    {
      "title": "The Strategic Purpose of Moonshots and Failures",
      "description": "Ben Gilbert and David Rosenthal highlight Google's history of colossal failures—including Google+, Wave, Buzz, numerous messaging apps, hot-air balloons, and Google Glass—raising the question of why a search giant pursued such diverse and speculative projects.",
      "timestamp": "00:01:53"
    },
    {
      "title": "The Valuation Dilemma of a Cash-Gushing Business",
      "description": "David Rosenthal uses a quote from the fictional character Russ Hanneman from HBO's Silicon Valley to illustrate the challenge facing profitable giants: while revenue is high, companies risk being pigeonholed as slow-growth 'dogs' compared to pre-revenue pure plays.",
      "timestamp": "00:04:00"
    }
  ],
  "speaker_background": [],
  "data_references": [
    {
      "item": "Year of Google's initial public offering",
      "value": "2004",
      "context": "Marks the transition of Google's cash-gushing search business into a publicly traded company."
    }
  ]
}
```

### After — revised prompt with exact contract feedback

Attempts: 1; latency: 2674 ms; deterministic contract passed: true.

```json
{
  "summary": "This briefing explores the foundational era of Google as an innovation factory, examining how a cash-gushing search business leveraged commodity hardware and breakthrough algorithms to build a massive financial engine. It highlights the strategic tension between Google's core revenue machine and its expansive, often speculative product experiments, setting the stage for its eventual reorganization into Alphabet right at the dawn of the AI era.",
  "topics": [
    {
      "title": "The Dual Identity and Strategic Paradox of Google",
      "description": "Google operates simultaneously as a cash-gushing search advertising business and an expansive innovation incubator. This creates a strategic tension between maintaining a dominant financial engine and pursuing high-risk moonshots, ranging from messaging apps and hot air balloons to Google Glass."
    },
    {
      "title": "The Evolution from Pure Play Search to Ecosystem Platform",
      "description": "In its early public days, Google faced the challenge of being pigeonholed as a single-product pure play. Over time, the company expanded its scope to act as the dominant platform company of the web era while attempting to structure its diverse product portfolio around its core mission of organizing the world's information."
    }
  ],
  "details": [
    {
      "title": "Google's Initial Foundations and Business Model",
      "description": "Ben Gilbert outlines how Google combined a breakthrough search algorithm with low-cost commodity hardware and search ads—described as the best business model of all time—to take the company public in 2004.",
      "timestamp": "00:00:51"
    },
    {
      "title": "The Spectrum of Google's Colossal Failures",
      "description": "Ben Gilbert and David Rosenthal review Google's history of high-profile product experiments and failures, including Google+, Google Wave, Buzz, numerous messaging apps, internet-beaming hot air balloons, and Google Glass.",
      "timestamp": "00:01:53"
    },
    {
      "title": "Framing the Alphabet Story Through Silicon Valley Fiction",
      "description": "David Rosenthal introduces a quote from the fictional character Russ Hanneman from Silicon Valley regarding the trap of public revenue versus pre-revenue potential, framing the public perception and valuation challenges Google faced around 2004 to 2006.",
      "timestamp": "00:04:00"
    }
  ],
  "speaker_background": [],
  "data_references": []
}
```
