"""
Generate 8 DUMMY resumes (5 PDFs incl. one image-only 'scanned' PDF + 3 .txt)
into data/resumes/. All names, emails (example.com) and phone numbers (555-xxxx)
are fictional — replace nothing with real personal data without consent.
"""

from pathlib import Path
import fitz  # PyMuPDF

OUT = Path(__file__).resolve().parents[1] / "data" / "resumes"
PAGE_W, PAGE_H, MARGIN, LINES_PER_PAGE = 612, 792, 54, 44

R1 = """AVA THOMPSON
Data Analyst
Phone: 555-0142 | Email: ava.thompson@example.com | Location: Portland, OR

SUMMARY
Data analyst with 4 years of experience turning messy data into clear
business decisions. Comfortable with SQL, Python, and dashboards.

EXPERIENCE
Bright Analytics, Data Analyst, 2021 - Present
- Built weekly revenue dashboards used by 3 product teams
- Cut report generation time by 40% by automating SQL pipelines
- Partnered with marketing to measure campaign lift across 12 channels
DataWorks Co., Junior Analyst, 2019 - 2021
- Cleaned and validated customer datasets of 2M+ rows
- Wrote documentation adopted as the team standard

SKILLS
SQL, Python (pandas, matplotlib), Tableau, Excel, statistics, A/B testing

EDUCATION
B.S. Economics, University of Oregon, 2019"""

R2 = """MARCUS LEE - SOFTWARE ENGINEER
Phone: 555-0177 | Email: marcus.lee@example.com | GitHub: github.com/marcuslee

SUMMARY
Backend-focused software engineer with 6 years of experience building
high-throughput services in Python and Go. I care about p99 latency,
clean interfaces, and boring, observable deployments.

EXPERIENCE
Northwind Labs, Senior Software Engineer, 2021 - Present
- Own the billing service handling 40k requests per second at p99 < 90ms
- Led migration from a monolith to 8 services with zero customer downtime
- Introduced structured logging and tracing; cut incident triage time in half
- Mentor 3 engineers and run the backend design review process
- Designed the idempotent payment retry system that cut duplicates to zero
- Drove adoption of contract tests between billing and checkout teams
Cloudline, Software Engineer, 2018 - 2021
- Built notification pipeline delivering 10M messages per day
- Reduced AWS spend by 28% by moving batch jobs to spot instances
- Wrote the company's first API style guide, still in use
- On-call rotation lead; authored 12 postmortems with action items
- Built internal CLI that cut new-service setup time from 2 days to 20 min

PROJECTS
queue-lite: a 900-star open-source job queue built on Redis streams
logvac: log compaction tool that shrinks ELK storage by 35%

SKILLS
Python, Go, PostgreSQL, Redis, Kafka, Docker, Kubernetes, AWS, Terraform

EDUCATION
B.S. Computer Science, University of Washington, 2018

CERTIFICATES
AWS Certified Solutions Architect - Associate (2022)

INTERESTS
Distributed systems, observability, mentoring junior engineers"""

R3 = """PRIYA    NAIR
Product     Manager
Phone: 555-0188        Email: priya.nair@example.com


SUMMARY
Product manager with 5 years in B2B SaaS. I ship     roadmap items that
move retention, not vanity metrics.


1

EXPERIENCE
Helio Software, Senior Product Manager, 2020 - Present
   - Own onboarding flow; lifted activation  from 41% to 58%
   - Ran 30+ customer interviews per quarter and turned findings into specs
Torvald Apps, Product Manager, 2018 - 2020
   - Launched mobile app to 100k downloads in year one

Page 1 of 1

SKILLS
Roadmapping, SQL,    Figma, analytics (Amplitude), stakeholder management

EDUCATION
MBA, Boston University, 2018
B.S. Information Systems, Northeastern, 2016"""

R4 = """DANIEL OKAFOR
DevOps Engineer
Phone: 555-0193 | Email: daniel.okafor@example.com

SUMMARY
DevOps engineer focused on reliable, repeatable infrastructure.

EXPERIENCE
Kite Cloud, DevOps Engineer, 2021 - Present
- Manage Kubernetes clusters for 25 services across 3 regions
- Cut deploy time from 25 min to 6 min with a new CI pipeline
- Introduced cost alerts that reduced cloud spend by 18%
StreamHost, Systems Administrator, 2019 - 2021
- Automated server provisioning with Ansible for 200+ hosts
- Achieved 99.95% uptime for the streaming platform

SKILLS
AWS, Terraform, Kubernetes, Ansible, GitHub Actions, Prometheus, Grafana

EDUCATION
B.Eng. Computer Engineering, University of Lagos, 2019"""

R5 = """SOFIA ROSSI
UX Researcher
Phone: 555-0160 | Email: sofia.rossi@example.com

SUMMARY
UX researcher with 3 years of experience in consumer apps.

EXPERIENCE
Lumen Apps, UX Researcher, 2022 - Present
- Ran 40 usability sessions informing the 2023 redesign
- Built a research repository used by 5 product squads
Studio Pi, Design Intern, 2021 - 2022
- Supported diary studies and survey design

SKILLS
Interviewing, usability testing, Figma, Dovetail, survey design

EDUCATION
M.S. Human-Computer Interaction, University of Milan, 2022"""

R6 = """EMILY CHEN
Marketing Specialist
Phone:\t555-0155   Email: emily.chen@example.com

SUMMARY\t
Marketing specialist with 4 years in content and lifecycle campaigns.

EXPERIENCE
Fielder Goods, Marketing Specialist, 2020 - Present
- Grew newsletter list from 8k to 45k subscribers
- Ran A/B tests on email subject lines lifting open rate by 9 points
Bluebird Agency, Content Coordinator, 2018 - 2020
- Wrote 120+ blog posts for SaaS and e-commerce clients

SKILLS
SEO, HubSpot, Google Analytics, copywriting, email marketing

EDUCATION
B.A. Communications, San Diego State, 2018"""

R7 = """OMAR HADDAD
QA Engineer
Phone: 555-0171 | Email: omar.haddad@example.com

SUMMARY
QA engineer specializing in test automation for web applications.

EXPERIENCE
Vertex Systems, QA Engineer, 2021 - Present
- Built Playwright suite covering 300+ scenarios, runs on every PR
- Reduced escaped defects by 35% year over year
Cobalt Retail, Manual QA Tester, 2019 - 2021
- Wrote test plans for checkout and inventory modules

SKILLS
Playwright, Selenium, pytest, Postman, Jira, SQL

EDUCATION
B.S. Computer Science, University of Jordan, 2019"""

R8 = """JANE   SMITH


Machine   Learning   Engineer


Phone: 555-0126   Email: jane.smith@example.com



SUMMARY
ML engineer with 5 years of experience shipping models to production.


EXPERIENCE
Orbital AI, Machine Learning Engineer, 2020 - Present
- Deployed ranking model serving 5M predictions per day
- Cut inference cost 30% with quantization and caching
Insight Retail, Data Scientist, 2018 - 2020
- Built demand-forecasting models adopted by 40 stores


SKILLS
Python, PyTorch, scikit-learn, Airflow, AWS SageMaker, MLflow

EDUCATION
M.S. Computer Science, Georgia Tech, 2018"""


def _add_page(doc, body, footer=None):
    page = doc.new_page(width=PAGE_W, height=PAGE_H)
    rect = fitz.Rect(MARGIN, MARGIN, PAGE_W - MARGIN, PAGE_H - MARGIN - 20)
    if page.insert_textbox(rect, body, fontname="helv", fontsize=10.5) < 0:
        raise SystemExit("Sample text too long for one page.")
    if footer:
        page.insert_text(fitz.Point(PAGE_W / 2 - 24, PAGE_H - 30), footer,
                         fontsize=9, fontname="helv")


def make_pdf(path: Path, text: str, numbered: bool = False):
    lines = text.strip("\n").split("\n")
    chunks = [lines[i:i + LINES_PER_PAGE] for i in range(0, len(lines), LINES_PER_PAGE)] or [[]]
    doc = fitz.open()
    for n, chunk in enumerate(chunks, 1):
        _add_page(doc, "\n".join(chunk),
                  footer=f"Page {n} of {len(chunks)}" if numbered else None)
    doc.save(path)
    doc.close()


def make_scanned_pdf(path: Path, text: str):
    """Render the resume as an image -> PDF with NO text layer (fake scan)."""
    tmp = fitz.open()
    _add_page(tmp, text)
    pix = tmp[0].get_pixmap(dpi=150)
    doc = fitz.open()
    page = doc.new_page(width=PAGE_W, height=PAGE_H)
    page.insert_image(fitz.Rect(0, 0, PAGE_W, PAGE_H), pixmap=pix)
    doc.save(path)
    doc.close()
    tmp.close()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    plan = [
        ("resume_01.pdf", make_pdf, R1),
        ("resume_02.pdf", lambda p, t: make_pdf(p, t, numbered=True), R2),  # 2 pages
        ("resume_03.pdf", make_pdf, R3),                                    # messy spacing
        ("resume_04.pdf", make_pdf, R4),
        ("scanned.pdf",   make_scanned_pdf, R5),                            # image-only
        ("resume_05.txt", lambda p, t: p.write_text(t.strip() + "\n", encoding="utf-8"), R6),
        ("resume_06.txt", lambda p, t: p.write_text(t.strip() + "\n", encoding="utf-8"), R7),
        ("resume_07.txt", lambda p, t: p.write_text(t.strip() + "\n", encoding="utf-8"), R8),
    ]
    for name, writer, text in plan:
        writer(OUT / name, text)
        print(f"created {OUT / name}")


if __name__ == "__main__":
    main()