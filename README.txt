EDUNOVA CLASS TEACHER LEAVE ROUTING
1. Back up the project and database.
2. Extract ALL files directly to C:\Users\Admin1\Desktop\AI_School_Management
3. Run:
   cd /d "C:\Users\Admin1\Desktop\AI_School_Management"
   python install_class_teacher_leave.py
4. Restart Flask: python app.py
5. Admin: http://127.0.0.1:5000/admin/class-teachers
6. Teacher: http://127.0.0.1:5000/teacher/student-leaves

Student leave: assigned class teacher ONLY; teacher leave: admin ONLY.
The new class_teacher_assignment table is created by existing db.create_all().
No existing leave records are deleted. Unassigned classes cannot submit new leave.
If a class teacher is reassigned, pending leave moves to the new teacher.
