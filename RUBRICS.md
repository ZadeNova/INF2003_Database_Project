# INF2003 Database Systems: Group Project Description

Transcribed from `INF2003_project_description.pdf` (SIT Internal, 6 pages) so the brief can be referenced without
re-uploading it. The wording is the module's; only formatting changed. Sections marked **Note (ours)** are added by the
team and are not part of the brief. If this file and the PDF ever disagree, the PDF wins.

## Key dates and limits (summary, ours)

| Item | Value |
|---|---|
| Team size | 5 (groups formed by end of week 2, 13 Sep 2026, 11:30 PM) |
| Project progress report (proposal) | Week 5, **4 Oct, 11:30 PM**; max 2 pages, Calibri (Body) 12, references excluded; single file |
| Final submission | Week 13, **29 Nov, 11:30 PM**; one `.zip` in the XSite group dropbox |
| Zip contents | Final report `*.pdf`, presentation slides `*.ppt(x)`, presentation video `*.mp4`, source code zip |
| Final report | Max 10 pages, Calibri (Body) 12, cover page, references and appendix excluded; XSite template |
| Video | Max 10 minutes at normal speed; every member presents; name shown on screen or slide |
| Late penalty | 20% per day per deliverable, unless an extension is granted before the deadline |
| Weighting | Group project is 50% of the module (25% relational, 25% non-relational); weighted by peer review |

## 1. Objectives

The objective of this group project is to design and develop a database application that makes use of both a relational
database and a non-relational database. The application must have a database management system (DBMS) as the backend and
would be better to have a graphical interface as the front-end. You need to explore the latest relational database
systems as well as NoSQL database. Through the project, you may need to review the theories and principles covered in
our module and apply them in a real-world scenario. You are free to design your application and are welcome to be
**innovative**. You are encouraged to use more datasets to run more interesting queries. Some dataset sources are here
for your reference:

- http://data.gov.sg
- https://www.kaggle.com/
- https://www.singstat.gov.sg/

## 2. Teams

The project will be conducted in a group of **5**. Groups are formed by self-enrolment, please form your group by end of
**week 2 (Sep 13, 11:30PM 2026)**. Unenrolled members will be automatically assigned to groups.

Each team member has a chance to do peer review at the end of the project. An email invitation on the peer review will
be sent out close to the project final submission period.

## 3. Tasks

A. **Identify an application.** You need to think of an application that involves two types of databases, relational and
   non-relational databases. You have the choice of either repeating the same functionalities using both databases, or
   using each database on different functions in the application.

B. **Identify datasets.** It is recommended to select real-world datasets. More dataset is preferred. In the
   implementation, you have the flexibility of using exactly the same set of data for both databases, or you can use
   different subsets of data for each database.

C. **Design the databases and application.** For relational database, construct the ER diagrams for your database, with
   different kinds of relationship (e.g., 1-to-many, many-to-1, and many-to-many) and types of data (e.g., strings,
   integers, etc.) For NoSQL database, you need to specify the schema and data model that are suitable for your data and
   application.

D. **Implement the application.** Your application should perform database construction and common database related
   functions such as CRUD. You are encouraged to design some complex functions to show your knowledge learnt in this
   module.

E. **Conduct necessary analysis and reflections.** You may include the performance analysis in terms of different aspects
   like speed and throughput. You may also discuss the problems and potential improvements.

## 4. Timeline and deliverables

The deliverables and their deadlines are shown in the table below. Time management is an important skill for everyone,
especially in a collaborative working environment. Please plan your tasks, manage your time, and submit your work as
scheduled.

| Deliverable | Description | Due and submission |
|---|---|---|
| Project progress report | A brief description of your application, data sets, current status and plans. **Maximum 2 pages.** | **Week 5, Oct 4, 11:30 PM.** XSite group Dropbox: single file within 2 pages |
| Project final report | A comprehensive report about the project. Including dataset, database design, implementation, discussion, and reflections. A project final report template is provided at x-site. **Maximum 10 pages.** | **Week 13, Nov 29, 11:30 PM.** XSite group dropbox: a `.zip` file containing final report `*.pdf`, presentation slides `*.ppt`, presentation video `*.mp4`, source code zip file (this cell spans the next four rows) |
| Project presentation slides | PowerPoint presentation `.pptx`. The PPT should be informative enough about the project details. | (as above) |
| Video presentation | Video presentation from **each** team member according to presentation slides. **Maximum 10 minutes.** | (as above) |
| Source code with user manual | Include the data and the source codes. The user manual shall describe the details about environment setup, configuration, and instructions to run the application. Readers shall be able to run the application by following the user manual. | (as above) |
| Peer review | Rating member's contribution through online survey/form. The invitation for peer review will be emailed to everyone close to the final submission. | (as above) |

### A. Project progress report

The proposal briefly describes your project application and plans to execute the project. Make sure your proposal is
within **2 pages** with Calibri (Body) Font size 12. (Excluding references). A template for the final report can be
downloaded from Xsite.

### B. Presentation slides and video

a. The slides and video to present and promote your application. Video should not exceed **10 minutes** in length (in
   **normal speed**). Penalty applies if the video exceeds 10-min as follows: 1) [11, 15) mins -> 3% penalty in the
   overall project marks; 2) [16, 20) mins -> 5% penalty; 2) [31, INF) mins -> 10% penalty.

b. All team members **MUST** present, but we do not enforce how much each member covers. Please indicate your name in
   your presentation (e.g., bottom-left of the screen or slides) to facilitate our marking process.

c. Presentation includes the following parts (order sensitive):

   i. **Background** (or your story), including application description, datasets description, and so on.

   ii. **Relational database** implementation description, function demo, and so on. We foresee most groups will have
       basic functions like simple insert, select, update. You are encouraged to highlight your advanced features,
       including DB design, constraints, complex queries, security, efficiency, etc.

   iii. **NoSQL database** implementation and demo. You may include your NoSQL design and tools used. Similarly, please
        also highlight your advanced features and your rigorous comparison between the SQL and NoSQL implementations.

   iv. (Optional) **Performance analysis.** You may also include the performance analysis of your implementations in
       terms of different aspects like speed and throughput.

### C. Final report

The final report should be comprehensive to cover all the information about the project. Please limit your report length
to **10 pages** with Calibri (Body) Font size 12. (Excluding cover page, references and appendix). A template for the
final report can be downloaded from Xsite.

### Source code

Please zip all the data, source code as well as the user manual into ONE (1) zip file. System libraries are not required
to submit, as they are large and quite meaningless regarding your database skills. If the size is too big (>2G) for LMS,
you can include a link to Github, but please make sure to grant the access permission.

### Late submission

For each deliverable, a penalty of **20% per day** will be imposed for late submission, unless an extension has been
granted by the module professors before the submission date. The extension request will be evaluated case-by-case.

### Plagiarism

The university's policy on copying does not allow you to copy software and your assessment solutions from another
person. It is the responsibility of all students that their assessment solutions are their work. You must also ensure
that others do not obtain access to your solutions to copy a part of them. Where such plagiarism is detected, both
assessments involved will receive a **ZERO** mark.

## 5. Assessment criteria

The group project will make up **50%** of your final grade (25% for relational database and 25% for non-relational
database). Overall, the project will be assessed based on the scope of the selected domain, the concepts and techniques
used, and their relevance. For example, use appropriate SQL constructs like simple queries, aggregate queries, integrity
constraints, views, and so on. The amount of data in the database should be sufficient for a complete and realistic
demonstration of the system. The final assessment will be **weighted by peer review**.

### Rubric

| | Excellent (>=80) | Good (<80 and >=60) | Average (<60 and 40) | Fail to meet expectations (<40) |
|---|---|---|---|---|
| **Project proposal (10%)** | The report is clear and comprehensive. Excellent description, coverage, and planning about the project. | The report is generally clear. Good description, coverage and planning on the project. | The report is unclear and not complete. Missing some information and planning details. | The report is very unclear, provides confusing information or little information and no planning details. |
| **Presentation quality (25%)**<br>Both video and ppt | The presentation is clear and logical. Excellent coverage and structure with clarity of explanation and details. Methods, analysis, results, conclusions are clearly stated. Implications of results and analysis are discussed. | The presentation is generally clear, mostly good report with explanation and details, some minor errors and ambiguities. Clear description of methods and some discussion of the results with some conclusions. | The presentation is unclear with less structure. Report organization is not well thought out. Partial explanation of methods and results, some errors and ambiguities. Some discussion of the results, little or no conclusions. | The presentation is very confusing and unclear. Brief and minimal report with little explanation and details. Nothing much done. |
| **Final report quality (25%)**<br>Final report | The report is clear and comprehensive. Excellent description, coverage, implementation details, analysis about the project. | The report is generally clear. Good description, coverage implementation details, analysis about the project. | The report is unclear and not complete. Missing some information and implementation details, analysis about the project. | The report is very unclear, provides confusing information or little information and no implementation details and analysis. |
| **Project quality and implementation (40%)**<br>Video + ppt + final report + source code | Interesting, innovative, accurate and useful database application and features. Appropriate & sufficient data sources are collected/used for the application. Significant implementation to both relational and NoSQL databases, appropriate choice of toolkits/API, algorithms and or complete implementation of modules. Excellent coding quality. | Minimum suitable datasets are collected/used. Appropriate and useful database-related tasks are performed. Good implementation to both relational and NoSQL databases, appropriate choice of toolkits/API for the working demo. Well tested and working. Good coding quality. | Very few features or use cases supported. Insufficient or inappropriate databases are used. Implementations are not always justified. The analysis did not come out with much useful information. Minor implementation for the database applications, limited features, may not work completely. Codes with some bad practices. | Total copy of existing idea, or nothing much done. Few features or use cases. Total copy of existing code, very little implementation, or nothing much done. Codes are wrongly implemented. |

### Extra credit

Extra credit available for **innovative** ideas, **advanced** technologies and user interfaces, and appropriate usage of
advanced SQL/NoSQL and DBMS features, e.g., complex queries like aggregates, nested queries, views, non-standard
integrity constraints, and even data analytics algorithms. You are welcome to talk to the module professors earlier to
have some comments.

## Note (ours): ambiguities in the brief

These are quirks in the source text, kept as written above. Treat the conservative reading as the rule.

- **Video penalty bands have gaps.** The brief lists [11, 15) → 3%, [16, 20) → 5%, [31, INF) → 10%. Nothing is stated for
  15 to 16 or 20 to 31 minutes, and the second band is numbered "2)" twice. Assume the penalty applies from 10:01 and
  stay under 10:00.
- **"Average (<60 and 40)"** is a typo for "<60 and >=40".
- **Rubric weights sum to 100%** (10 + 25 + 25 + 40). The 25% / 25% relational and non-relational split above is a
  separate statement about the group project's share of the module grade, so both databases carry equal weight.
- **Zip file extensions.** The deliverable table says slides `*.ppt`; the slides row says `.pptx`. Submit `.pptx`.
- **Source-code size.** If the zip exceeds 2 GB, a GitHub link with access granted is allowed instead.
- **Plagiarism clause** applies to copying from another person and to others copying from us, so the repository stays
  private.
