"""Classifier checks built from real job emails (subject, opening text, sender), with names and companies changed."""

import pytest

from jobtracker.classify import classify, same_company

CASES = [
    # (subject, body, sender name, sender address) -> (kind, company, role contains)
    (("Thank you for applying to Brightloom!",
      "Hi Alex, Thank you for your application for the Intern, Software Engineering position! At Brightloom, we're all about",
      "", "no-reply@brightloom.com"),
     ("applied", "Brightloom", "Intern, Software Engineering")),
    (("Kitewire | Confirmation on your Application + CodeSignal",
      "Hi Alex, Thank you for taking the time to apply to our Software Engineer opening at Kitewire! Your application has been received and will be reviewed as soon as you complete the CodeSignal assessment",
      "Kitewire Talent Team", "no-reply@ashbyhq.com"),
     ("assessment", "Kitewire", "Software Engineer")),
    (("Your application - Software Engineering Intern (Summer) at Lanternfish",
      "Hi Alex, Thanks again for your interest in Lanternfish and the Software Engineering Intern (Summer) role. We sincerely appreciate you taking the time to apply with us, but we have decided not to move forward with your application.",
      "Lanternfish Recruiting", "no-reply@recruiting.lanternfishhq.com"),
     ("rejected", "Lanternfish", "Software Engineering Intern")),
    (("Halberd Application Update – Req: R100234",
      "Dear Alex, Thank you for considering a career opportunity with Halberd. Unfortunately, we will not be moving forward with your application at this time for R100234 Engineering Internship / Co-Op",
      "Halberd Workday", "Halberd@myworkday.com"),
     ("rejected", "Halberd", "")),
    (("Alex, your application was sent to QUILLWORKS", "Your application was sent to QUILLWORKS", "LinkedIn", "jobs-noreply@linkedin.com"),
     ("applied", "QUILLWORKS", "")),
    (("Your application was viewed by Wren", "Your application was viewed by Wren", "LinkedIn", "jobs-noreply@linkedin.com"),
     ("viewed", "Wren", "")),
    (("Your application to Software Engineer, Quality [SDET] at NovaLedger",
      "Unfortunately, NovaLedger has decided not to move forward with your application.", "LinkedIn", "jobs-noreply@linkedin.com"),
     ("rejected", "NovaLedger", "Software Engineer, Quality")),
    (("Indeed Application: Software Engineers",
      "Your application has been submitted. Good luck!\nApplication submitted Software Engineers ZQT Inc - Manhattan, NY 10007 The following items were sent to ZQT Inc. Good luck!",
      "Indeed Apply", "indeedapply@indeed.com"),
     ("applied", "ZQT", "Software Engineers")),
    (("Invitation | Holloway x Codility Coding Assessment",
      "Dear Alex, Thank you again for your interest in Holloway and your application to the 2027 Corporate Technology Summer Internship Program opportunity. As part of the application process, you are invited to complete",
      "", "noreply@holloway.tal.net"),
     ("assessment", "Holloway", "")),
    (("Application Update from Aero Kinetica",
      "Hello Alex, Thank you for your interest in the Flight Software Engineer position at Aero Kinetica. We appreciate the time and effort you put into your application, and wanted to let you know that this position has now been filled.",
      "Aero Kinetica Hiring Team", "no-reply@ashbyhq.com"),
     ("rejected", "Aero Kinetica", "Flight Software Engineer")),
    (("Thank you from BLX Consulting - 2027 Intern - Technology",
      "Hi Alex, Thank you for your interest in BLX Consulting and for applying to 2027 Intern - Technology, one of our Early Talent positions! At this time, you have not been selected to move forward in our application process.",
      "BLX Consulting Early Talent Team", "blxconsulting@myworkday.com"),
     ("rejected", "BLX Consulting", "")),
    (("Thank You for Your Interest in KRW",
      "Dear Alex Thank you for your interest in career opportunities with KRW. Unfortunately, we have closed the JR1234 Junior Software Engineer position and will not be filling this role.",
      "hrhelpdesk krwinc", "krwinc@myworkday.com"),
     ("rejected", "KRW", "")),
    (("Thank you for applying to PlateRun",
      "Hi Alex, Thank you for applying to PlateRun's Machine Learning Intern (Masters) - Summer 2027 position! We've received your application. Unfortunately, due to volume we can't respond to every applicant.",
      "", "no-reply@platerun.com"),
     ("applied", "PlateRun", "")),
    (("LTC invites you to complete a Criteria Assessment - SE Intern",
      "Hi Alex, Thank you for your interest in joining Lakefront Trading Company (LTC)! We are excited to invite you to the next stage in our recruitment process",
      "LTC Campus Recruiting Team", "DO-NOT-REPLY@criteriacorp.com"),
     ("assessment", "LTC", "")),
    (("Next Steps: Technical Assessment for 2027 Applied AI Engineer Intern, New York Internship | Centennial Management",
      "Hi Alex, Thank you for your interest in the Engineering & AI Internship role. As the next step in your application process, we'd like you to complete our technical assessment, powered by HackerRank.",
      "Centennial HR", "cmg@myworkday.com"),
     ("assessment", "Centennial", "")),
    (("Video Interview with Alex Kim (Referral) - JR1234 Junior Software Engineer",
      "Platform: Microsoft Teams Please confirm that you have received the invitation.",
      "Jordan Price", "Jordan.Price@krwinc.com"),
     ("interview", "KRW", "")),
    (("Thank you for applying to Ashworth!",
      "Dear Alex, Thank you for submitting an application for the position of Consultative Offerings - Government & Public Services - Summer Scholar - AI and Data Engineering, 300100.",
      "Recruiting at Ashworth", "donotreply@ashworth.com"),
     ("applied", "Ashworth", "Summer Scholar")),
    (("Alex, thank you for your application to Calloway & Company",
      "Dear Alex, Thank you for your interest in the Business Analyst role at Calloway.",
      "Calloway Recruiting", "calloway_recruiting@calloway.com"),
     ("applied", "Calloway", "")),
    (("Assessment completed: Kitewire 2025 Coding Assessment",
      "Hi Alex, You have completed the Kitewire 2025 Coding Assessment on November 12th.", "CodeSignal", "no-reply@codesignal.com"),
     ("assessment_done", "Kitewire", "")),
    (("Interview invitation – 2027 Applied AI Engineer Intern",
      "Hi Alex, Thank you for completing the HackerRank. We'd like to schedule an interview with you for the 2027 Applied AI Engineer Intern role at Centennial.",
      "Centennial HR", "cmg@myworkday.com"),
     ("interview", "Centennial", "")),
    (("BLX Consulting Pre-Recorded Video Interview Request - 2027 Intern - Technology",
      "Hi Alex, You have been selected to complete a pre-recorded video interview (PRVI) for the 2027 Intern - Technology role.",
      "Olivia from BLX Consulting", "TalentAcquisition@blxconsulting.com"),
     ("assessment", "BLX Consulting", "")),
    (("Big Tech Layoffs Hit Quant?", "Bastion built an AI system...", "WallStreetQuants", "info@thewallstreetquants.com"),
     ("other", None, None)),
]


@pytest.mark.parametrize("args,expected", CASES, ids=[c[0][0][:40] for c in CASES])
def test_classify_real_emails(args, expected):
    got = classify(*args)
    kind, company, role = expected
    assert got.kind == kind
    if company is not None:
        assert same_company(got.company, company), f"company {got.company!r} vs {company!r}"
    if role:
        assert role.lower() in got.role.lower(), f"role {got.role!r}"


def test_company_matching():
    assert same_company("Lakefront Trading Company (LTC)", "LTC")
    assert same_company("KRW", "Krwinc")
    assert same_company("Calloway & Company", "Calloway")
    assert same_company("ZQT Inc", "ZQT")
    assert not same_company("Intel", "Intellect Design")
    assert same_company("Centennial", "Centennial Management")
    assert same_company("Lanternfish", "Lanternfishhq")
