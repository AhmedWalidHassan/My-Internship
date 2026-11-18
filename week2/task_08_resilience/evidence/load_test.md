## Load test: 50 requests over 30 s (1.67 req/s offered)

| p50 | p95 | Error rate | Point where it degrades |
|---:|---:|---:|---|
| 63.6 s | 77.3 s | 70% (35/50) | request #3 (sent at 1.2 s, ~2.50 req/s so far): request_timeout after 60.8 s |

Outcomes: {'ok': 15, 'request_timeout': 24, 'verification_unavailable': 11}. Completed 15 answers in 108 s wall clock = 0.14 answers/s served. Latency of the first five: 4.2, 12.9, 63.6, 64.2 s.

| # | sent at | latency | result |
|---:|---:|---:|---|
| 1 | 0.0 s | 4.2 s | ok |
| 2 | 0.6 s | 12.9 s | ok |
| 3 | 1.2 s | 60.8 s | request_timeout |
| 4 | 1.8 s | 64.2 s | ok |
| 5 | 2.4 s | 63.6 s | ok |
| 6 | 3.0 s | 63.0 s | ok |
| 7 | 3.6 s | 62.4 s | ok |
| 8 | 4.2 s | 61.8 s | ok |
| 9 | 4.8 s | 61.2 s | ok |
| 10 | 5.4 s | 60.6 s | request_timeout |
| 11 | 6.0 s | 61.2 s | request_timeout |
| 12 | 6.6 s | 61.3 s | verification_unavailable |
| 13 | 7.2 s | 60.9 s | verification_unavailable |
| 14 | 7.8 s | 60.7 s | verification_unavailable |
| 15 | 8.4 s | 60.6 s | verification_unavailable |
| 16 | 9.0 s | 57.0 s | ok |
| 17 | 9.6 s | 61.4 s | verification_unavailable |
| 18 | 10.2 s | 60.5 s | verification_unavailable |
| 19 | 10.8 s | 60.6 s | request_timeout |
| 20 | 11.4 s | 60.8 s | verification_unavailable |
| 21 | 12.0 s | 60.9 s | verification_unavailable |
| 22 | 12.6 s | 61.3 s | request_timeout |
| 23 | 13.2 s | 61.4 s | request_timeout |
| 24 | 13.8 s | 63.2 s | request_timeout |
| 25 | 14.4 s | 60.8 s | request_timeout |
| 26 | 15.0 s | 60.6 s | request_timeout |
| 27 | 15.6 s | 60.6 s | request_timeout |
| 28 | 16.2 s | 61.4 s | request_timeout |
| 29 | 16.8 s | 61.2 s | verification_unavailable |
| 30 | 17.4 s | 60.6 s | request_timeout |
| 31 | 18.0 s | 61.2 s | request_timeout |
| 32 | 18.6 s | 61.3 s | request_timeout |
| 33 | 19.2 s | 61.1 s | request_timeout |
| 34 | 19.8 s | 60.8 s | request_timeout |
| 35 | 20.4 s | 62.8 s | request_timeout |
| 36 | 21.0 s | 61.2 s | request_timeout |
| 37 | 21.6 s | 60.8 s | request_timeout |
| 38 | 22.2 s | 61.1 s | request_timeout |
| 39 | 22.8 s | 60.8 s | request_timeout |
| 40 | 23.4 s | 60.9 s | verification_unavailable |
| 41 | 24.0 s | 60.8 s | request_timeout |
| 42 | 24.6 s | 60.6 s | verification_unavailable |
| 43 | 25.2 s | 67.6 s | request_timeout |
| 44 | 25.8 s | 68.6 s | request_timeout |
| 45 | 26.4 s | 71.9 s | ok |
| 46 | 27.0 s | 74.8 s | ok |
| 47 | 27.6 s | 74.5 s | ok |
| 48 | 28.2 s | 80.0 s | ok |
| 49 | 28.8 s | 76.1 s | ok |
| 50 | 29.4 s | 75.6 s | ok |
