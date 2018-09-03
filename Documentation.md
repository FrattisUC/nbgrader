# Frattis Project Documentation

## Motitation for this Documentation

We are currently working on an adaptation of both JupyterHub and Nbgrader for use on evaluations and other formal academic instances that require the students to work with notebooks. While the current solution offered by team Jupyter is great, it doesn't adjust to our needs, specifically on terms of security and registration on different courses, and thus this project was born. Currently we are on "pre-alpha" development, but we are doing our best <3

## Starting State of the Project

### User Hierarchy

Currently we are working with 2 types of users, which are already present on JupyterHub/Nbgrader, but do not have all the setup we required.

### Students

The core of the system, students are users that subscribe to different courses so they have access to different assignments through the semester. Currently implemented by JHub/Nbg, although they have several flaws we need to change so they are usable in a real scenario:

* They have complete access to system files, and to the rubrics of the different evaluations of the courses. This is partly because of how Nbgrader handles the exchange folder, where graders put assignments and students retrieve and deliever their assignments: currently the system needs mode 777 on said folder and contents, which means any user can see and write any file and folder in there. While this is "worked around" with the use of containers, any external user can still retrieve or modify data via ssh.

* They can only be susbcribed to one course at a time. The way Nbgrader currently handles this is via a configuration file located in a hidden folder in /home/{username}. For a student to see the assignments for a given course, they must change the configuration file so it reflects the course id from where they want to retrieve their assignments. There's a [proposed solution on GitHub](https://github.com/jupyter/nbgrader/issues/544), which we plan to include in this project.

  * An alternative to this is to "open up" the courses, so all students have access to all courses at all times, being able to retrieve and answer assignments on all courses they want. The problem with this solution is that it does not scale well (with 100+ courses the student must search deeply for a particular course), and that they are also able to answer assignments from courses they are not currently signed in: clearly this is not desired as it may lead to potential security flaws.

Currently users are registered in a user group, jupyterstudents, on the system server, where they are granted access to their homes and corresponding files. **This is important** as this is the way we currently handle the whitelist for access.

### Graders

Users that can create, deliver and correct assignments in the system. Currently this users belong to both the user groups jupyterstudents and jupyteradmins, since in the context of this project graders of one course normally are students in another course.

Currently implemented in Nbgrader, but we differ in how they are implemented from their intended purpouse:

* Originally they are intended to be external users that do not attend to any course, since they have full access to the rubrics, grades and personal information of the students (there's also a configuration option in jupyterhub that allows them to see the student's home contents). While this is plausible, it does not apply to our problem context, in which graders are also students in different courses most of the time.

* Graders have their own nbgrader configuration file in which they point to the course they work on. While this is good when the relation is 1:N (one course has many graders, but graders belong to only one course), this bring problems if we "open up" the courses as said before: graders have access to all courses, so they can potentially grade courses where they are not actually graders!.

* It is important to consider aswell that in our case, where graders are also students, it is critically important to restrict the access graders currently have: potentially a grader may have access to a course where he is student, and alter his/her grades on purpouse.

## Proposed Changes for this Project

### Student-Course & Grader-Course Tables

The relation between students, graders and courses will be recorded in the schemas studentenrollment and graderenrollment. Each schema will contain tables that reflect for each period of time (semesters in our case) who's enrolled in which course, reflecting if said user is a student or a grader. For example, studentenrollment.2018_2 will list all students and the courses they are enrolled in.

For each table, the columns will be *student_id/grader_id*, depending of which table you are in, and *course_id*. *student_id/grader_id* is the email of said user, while *course_id* is the the assigned id for the course. Both are strings, and required.

**It is important to note that the home folder of each user will be same as their student_id, without the domain (i.e. user1@gmail.com will have user1 as home folder). Keep this in mind when enrolling students.**

### Database Keeper Service

Default: PSQL database.
(Connect to the db: psql --host=localhost --dbname=nbgrader --username=nbgrader)

This service, currently non-existant in Jupyterhub/Nbgrader, serves as a support for the [proposed solution on Github](https://github.com/jupyter/nbgrader/issues/544). As we plan to use schemas that keep track of the relation between students and courses, and between graders and courses, we need to limit access of the users within said schemas: whenever a user tries to access, it will be done via this service that will check if said user has the permission to modify or read it.

User cases that serve for motivation for the inclusion of this service:
  
* A grader wants to add or delete an user from his/her own course on the DB, since a student dropped the course in the middle of the semester, or registered said course extra-oficially. The keeper checks if the grader has such access, before letting the action from said grader take effect.

* Grader wants to deliver/retrieve assignments to/from the students. They need to access the DB for a list of students that are enrrolled in said course, so he can deliver the assignments. The keeper must check first that the grader does have authorization to see the students, before returning the information.

### Student and Graders responsabilities

One of the things that motivated this project is the difference in the philosophy on how to treat students, and how to manage the files in the server. Normally, the system assumes that students can be trusted with sensible files, since they have access to the exchange folder in order to retrieve/deliver their assignments. The grader's role consists in creating, validating and assigning the assignment in the different courses, and collecting them, from the exchange folder, for grading and feedback.

For this project, we drop the assumption of trusted users. As we plan to implement the system in a real education institue, we must keep in mind that both students and graders may not be fully trustworthy: we must limit their access to *only the information and files they need*, without restricting them unnecesarily.

In order to achieve this, we will limit the access of students and graders, while increasing the amount of work graders must do to complete the cycle of assignments. Some things we must change;

* Students must have access *only* to their home folder, and the contents within there. They should not be able to access the exchange folder, or sensible information via ssh or any other way.

* Students should be able to request partial grading during the completition of an assignment, so they can tell how well they are doing in an specific moment.

* Graders should deliver assignments to each student individually, checking in the database who's in which course, and when they retrieve them for grading, they must collect them individually (and save them in a system folder outside the student's access)

## To-Do list

* [ ] Set correctly the permissions for the exchange folder (only graders can access said folder and its contents), and re-configure nbgrader so it accepts this new way of treating the folder.
* [ ] Create a DB that reflects the relation between students and courses, and between graders and courses.
* [ ] Ensure graders cannot access courses where they are not graders.
* [ ] Ensure students can only access their home directories.
* [ ] Create the DB keeper service.
* [ ] Graders' ability to push to the students' repositories.
* [ ] Graders' ability to pull from the student's repositories.
* [ ] Change the front-end, so the graders' view reflect this changes.
* [ ] Allow graders to set timers so the pull-push is done automatically.
* [ ] Improve how nbgrader delivers feedbacks, depending on the context of the situation.
* [ ] Allow users to request a review of their current answers, so they can check mid-evaluation the correctness of their evaluations.