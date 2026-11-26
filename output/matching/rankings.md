# Candidate ranking (Task 2 - Job Description Matching)

Score = mean of 2 runs at temperature 0 (prompt match_v1; rubric: 10/required skill, 8/preferred, 10/5/0 experience).

## Data Analyst (Cobalt Health (fictional))

| Rank | Candidate | Score | Run1/Run2 (delta) | Matched | Missing required |
|---|---|---|---|---|---|
| 1 | AVA THOMPSON | 66 | 66/66 (0) | 6 | - |
| 2 | MARCUS LEE | 28 | 28/28 (0) | 2 | Excel, statistics, Tableau |
| 2 | OMAR HADDAD | 28 | 28/28 (0) | 2 | Excel, statistics, Tableau |
| 2 | PRIYA NAIR | 28 | 28/28 (0) | 2 | Excel, statistics, Tableau |
| 5 | JANE SMITH | 18 | 18/18 (0) | 1 | SQL, Excel, statistics, Tableau |
| 6 | DANIEL OKAFOR | 10 | 10/10 (0) | 0 | SQL, Excel, statistics, Tableau |
| 6 | EMILY CHEN | 10 | 10/10 (0) | 0 | SQL, Excel, statistics, Tableau |

## Python Developer (Brightlane Logistics (fictional))

| Rank | Candidate | Score | Run1/Run2 (delta) | Matched | Missing required |
|---|---|---|---|---|---|
| 1 | MARCUS LEE | 56 | 56/56 (0) | 5 | Git, REST APIs |
| 2 | OMAR HADDAD | 38 | 38/38 (0) | 3 | Docker, Git, REST APIs |
| 3 | AVA THOMPSON | 30 | 30/30 (0) | 2 | Docker, Git, REST APIs |
| 4 | JANE SMITH | 28 | 28/28 (0) | 2 | SQL, Docker, Git, REST APIs |
| 5 | DANIEL OKAFOR | 26 | 26/26 (0) | 2 | Python, SQL, Docker, Git, REST APIs |
| 6 | PRIYA NAIR | 20 | 20/20 (0) | 1 | Python, Docker, Git, REST APIs |
| 7 | EMILY CHEN | 10 | 10/10 (0) | 0 | Python, SQL, Docker, Git, REST APIs |

## Consistency check (2 runs per pair, temperature 0)
- identical (delta 0): 14 pairs
- minor drift (1-2 pts): 0 pairs
- INCONSISTENT (>2 pts): 0 pairs

## Excluded resumes
- scanned.pdf - no text found (scanned file)

Fairness review: see qa/fairness_note.md