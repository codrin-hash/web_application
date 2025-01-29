import datetime

from flask import Flask, render_template, request, redirect, url_for, flash, session
import cx_Oracle

cx_Oracle.init_oracle_client(lib_dir=r"C:\Users\codri\instantclient_19_9")
app = Flask(__name__)
app.secret_key = "supersecretkey"

# Configurare conexiune Oracle
dsn = cx_Oracle.makedsn("bd-dc.cs.tuiasi.ro", 1539, service_name="ORCL")
try:
    conn = cx_Oracle.connect(user="BD164", password="master2004", dsn=dsn)
    print("Conexiune cu baza de date reușită!")
except Exception as e:
    print("Eroare la conectare:", str(e))

cursor = conn.cursor()

@app.route('/')
def home():
    return render_template('dashboard.html')

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name")
        phone = request.form.get("phone")
        email = request.form.get("email")

        try:
            cursor = conn.cursor()
            query = """
                INSERT INTO CUSTOMERS (NAME, PHONENUMBER, EMAIL)
                VALUES (:name, :phone, :email)
            """
            cursor.execute(query, {"name": name, "phone": phone, "email": email})
            conn.commit()
            cursor.close()

            flash("Registration successful!", "success")
            return redirect(url_for("login"))
        except cx_Oracle.IntegrityError:
            flash("Email already exists. Please use a different one.", "danger")
        except Exception as e:
            flash(f"An error occurred: {str(e)}", "danger")

    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        phone = request.form.get("phone")

        try:
            # Verificarea existentei utilizatorului in tabela CUSTOMERS
            cursor = conn.cursor()
            query = """
                SELECT CUSTOMERID, NAME 
                FROM CUSTOMERS 
                WHERE EMAIL = :email AND PHONENUMBER = :phone
            """
            cursor.execute(query, {"email": email, "phone": phone})
            user = cursor.fetchone()
            cursor.close()

            if user:
                customer_id = user[0]
                customer_name = user[1]
                session["user_id"] = customer_id
                session["user_name"] = customer_name

                cursor = conn.cursor()
                # Verificam daca utilizatorul are un profil completat
                query = """
                    SELECT PROFILEID FROM PROFILES WHERE CUSTOMERID = :customer_id
                """
                cursor.execute(query, {"customer_id": customer_id})
                profile = cursor.fetchone()
                cursor.close()

                if profile:
                    flash(f"Welcome back, {customer_name}!", "success")
                    # Redirectionează la pagina de detalii ale contului
                    return redirect(url_for("profile"))
                else:
                    flash("Please complete your profile.", "warning")
                    return redirect(url_for("complete_profile", customer_id=customer_id))

            else:
                flash("Invalid email or phone number. Please try again.", "danger")
        except Exception as e:
            flash(f"An error occurred: {str(e)}", "danger")

    return render_template("login.html")

@app.route("/complete_profile/<int:customer_id>", methods=["GET", "POST"])
def complete_profile(customer_id):
    if request.method == "POST":
        age = request.form.get("age")
        height = request.form.get("height")
        weight = request.form.get("weight")

        try:
            cursor = conn.cursor()

            # Obtinem valoarea urmatoare pentru PROFILEID din SEQUENCE
            cursor.execute("SELECT profile_id_seq.NEXTVAL FROM DUAL")
            profile_id = cursor.fetchone()[0]

            query = """
                INSERT INTO PROFILES (PROFILEID, CUSTOMERID, AGE, HEIGHT, WEIGHT)
                VALUES (:profile_id, :customer_id, :age, :height, :weight)
            """
            cursor.execute(query, {"profile_id": profile_id, "customer_id": customer_id, "age": age, "height": height, "weight": weight})
            conn.commit()
            cursor.close()

            flash("Profile updated successfully!", "success")
            return redirect(url_for('profile'))  # Redirectionare catre detalii abonament

        except Exception as e:
            flash(f"An error occurred: {str(e)}", "danger")

    return render_template("complete_profile.html", customer_id=customer_id)

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']

    cursor.execute("SELECT * FROM CUSTOMERS WHERE CUSTOMERID = :1", [user_id])
    user = cursor.fetchone()

    cursor.execute("SELECT * FROM subscriptions")
    subscriptions = cursor.fetchall()

    return render_template('dashboard.html', user=user, subscriptions=subscriptions)

@app.route("/profile", methods=["GET", "POST"])
def profile():
    # Verifica dacă utilizatorul este autentificat
    if "user_id" not in session:
        flash("Please log in first.", "danger")
        return redirect(url_for("login"))  # Redirectionare la login daca nu este autentificat

    user_id = session["user_id"]
    can_plan_workout = False  # Variabila pentru a controla daca utilizatorul poate planifica un antrenament

    try:
        with conn.cursor() as cursor:
            # Obtine datele utilizatorului
            cursor.execute("""
                SELECT NAME, EMAIL, PHONENUMBER
                FROM CUSTOMERS
                WHERE CUSTOMERID = :user_id
            """, {"user_id": user_id})
            user_data = cursor.fetchone()

            if not user_data:
                flash("User not found.", "danger")
                return redirect(url_for("login"))  # Daca nu exista utilizator, redirectioneaza la login

            # Obtine datele profilului
            cursor.execute("""
                SELECT AGE, HEIGHT, WEIGHT
                FROM PROFILES
                WHERE CUSTOMERID = :user_id
            """, {"user_id": user_id})
            profile_data = cursor.fetchone()

            # Obtine tipul si statusul abonamentului
            cursor.execute("""
                SELECT SUBSCRIPTIONTYPE, STATUS
                FROM SUBSCRIPTIONS
                WHERE SUBSCRIPTIONID = (
                    SELECT SUBSCRIPTIONID
                    FROM CUSTOMERS
                    WHERE CUSTOMERID = :user_id
                )
            """, {"user_id": user_id})
            subscription_data = cursor.fetchone()

            # Verifica daca utilizatorul are un abonament activ de tip Gold
            if subscription_data:
                subscription_type, subscription_status = subscription_data
                if subscription_type == 'Gold' and subscription_status == 'Active':
                    can_plan_workout = True
                else:
                    flash("You need a Gold subscription to plan a workout.", "danger")

            # Planificarea unui antrenament daca se face un POST
            if request.method == "POST":
                trainer_id = request.form["trainer_id"]
                workout_type = request.form["workout_type"]
                session_date = request.form["session_date"]

                try:
                    # Inserarea antrenamentului planificat in baza de date
                    cursor.execute("""
                        INSERT INTO PLANNED_WORKOUTS (CUSTOMERID, TRAINERID, WORKOUTTYPE, SESSIONDATE)
                        VALUES (:customer_id, :trainer_id, :workout_type, TO_DATE(:session_date, 'YYYY-MM-DD HH24:MI'))
                    """, {
                        "customer_id": user_id,
                        "trainer_id": trainer_id,
                        "workout_type": workout_type,
                        "session_date": session_date
                    })
                    conn.commit()
                    flash("Workout successfully planned!", "success")
                    return redirect(url_for("profile"))  # Redirectioneaza la profil dupa planificare

                except Exception as e:
                    flash(f"An error occurred while planning the workout: {str(e)}", "danger")
                    return redirect(url_for("profile"))

            # Afiseaza sesiunile planificate ale utilizatorului
            cursor.execute("""
                SELECT pw.PLANNEDWORKOUTID, pw.WORKOUTTYPE, t.TRAINER_NAME, pw.SESSIONDATE
                FROM PLANNED_WORKOUTS pw
                JOIN TRAINERS t ON pw.TRAINERID = t.TRAINERID
                WHERE pw.CUSTOMERID = :user_id
            """, {"user_id": user_id})
            planned_workouts = cursor.fetchall()

        return render_template("profile.html",
                               user_data=user_data,
                               profile_data=profile_data,
                               subscription_data=subscription_data,
                               can_plan_workout=can_plan_workout,
                               planned_workouts=planned_workouts)

    except Exception as e:
        flash(f"An error occurred: {str(e)}", "danger")
        return redirect(url_for("profile"))

@app.route("/delete_workout/<int:workout_id>", methods=["POST"])
def delete_workout(workout_id):
    if "user_id" not in session:
        flash("Please log in first.", "danger")
        return redirect(url_for("login"))

    try:
        with conn.cursor() as cursor:
            # Sterge sesiunea de antrenament din baza de date
            cursor.execute("""
                DELETE FROM PLANNED_WORKOUTS
                WHERE PLANNEDWORKOUTID = :workout_id AND CUSTOMERID = :user_id
            """, {"workout_id": workout_id, "user_id": session["user_id"]})
            conn.commit()
            flash("Workout session deleted successfully.", "success")
            return redirect(url_for("profile"))  # Redirectionează la profil dupa stergere

    except Exception as e:
        flash(f"An error occurred: {str(e)}", "danger")
        return redirect(url_for("login"))

@app.route("/choose_subscription", methods=["GET", "POST"])
def choose_subscription():
    if request.method == "POST":
        # Preluam tipul de abonament selectat din formular
        subscription_type = request.form.get("subscription_type")
        customer_id = session.get("user_id")  # Presupunem ca user_id este stocat in sesiune

        print("Customer ID from session:", customer_id)
        print("Subscription type selected:", subscription_type)

        if subscription_type and customer_id:
            try:
                # Preluam data curenta
                start_date = datetime.datetime.now()
                # Data de finalizare
                end_date = start_date + datetime.timedelta(days=30)

                print(f"Inserting subscription {subscription_type} into SUBSCRIPTIONS table")

                # Inseram abonamentul in tabela SUBSCRIPTIONS
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO SUBSCRIPTIONS (SUBSCRIPTIONTYPE, STARTDATE, ENDDATE, STATUS)
                    VALUES (:subscription_type, :start_date, :end_date, 'Active')
                """, {"subscription_type": subscription_type, "start_date": start_date, "end_date": end_date})
                conn.commit()

                print("Subscription inserted successfully!")

                # Preluam ID-ul abonamentului inserat
                cursor.execute("""
                    SELECT SUBSCRIPTIONID FROM SUBSCRIPTIONS WHERE SUBSCRIPTIONTYPE = :subscription_type
                """, {"subscription_type": subscription_type})
                subscription_id = cursor.fetchone()[0]

                # Verificam daca abonamentul a fost inserat cu succes
                cursor.execute("SELECT COUNT(*) FROM SUBSCRIPTIONS WHERE SUBSCRIPTIONID = :subscription_id",
                               {"subscription_id": subscription_id})
                result = cursor.fetchone()[0]

                if result > 0:
                    print(f"Subscription with ID {subscription_id} exists.")
                else:
                    print(f"Subscription with ID {subscription_id} does not exist.")

                print("Inserted Subscription ID:", subscription_id)

                # Actualizam tabelul CUSTOMERS cu ID-ul abonamentului si schimbam starea
                print(f"Updating customer {customer_id} with subscription ID {subscription_id}")

                # Verificam ca customer_id exista in tabela CUSTOMERS
                cursor.execute("SELECT COUNT(*) FROM CUSTOMERS WHERE CUSTOMERID = :customer_id",
                               {"customer_id": customer_id})
                customer_exists = cursor.fetchone()[0]

                if customer_exists > 0:
                    try:
                        # Actualizam tabelul CUSTOMERS cu ID-ul abonamentului si starea
                        cursor.execute("""
                            UPDATE CUSTOMERS
                            SET SUBSCRIPTIONID = :subscription_id, SUBSCRIPTIONSTATUS = 'Yes'
                            WHERE CUSTOMERID = :customer_id
                        """, {"subscription_id": subscription_id, "customer_id": customer_id})
                        conn.commit()
                        print("Customer updated successfully!")
                    except Exception as e:
                        print("Error executing UPDATE:", str(e))
                else:
                    print(f"Customer with ID {customer_id} does not exist.")

                # Flash mesaj de succes
                flash(f"Subscription '{subscription_type}' added successfully and status updated!", "success")
                return redirect(url_for('profile'))  # Redirectionăm la profilul utilizatorului

            except cx_Oracle.DatabaseError as e:
                error, = e.args
                flash(f"An error occurred: {error.message}", "danger")
                return redirect(url_for('choose_subscription'))

    return render_template("choose_subscription.html")

@app.route("/logout")
def logout():
    # Sterge datele din sesiune pentru a deconecta utilizatorul
    session.pop("user_id", None)
    session.pop("user_name", None)
    flash("You have been logged out successfully.", "success")
    return redirect(url_for("login"))  # Redirectioneaza utilizatorul la pagina de login

@app.route("/select_workout", methods=["GET", "POST"])
def select_workout():
    if "user_id" not in session:
        flash("Please log in first.", "danger")
        return redirect(url_for("login"))

    workout_sessions = []
    try:
        cursor = conn.cursor()

        # Obtine sesiunile disponibile
        cursor.execute("""
            SELECT SESSIONID, SESSIONNAME, DATEOFSESSION, MAXPARTICIPANTS, AVAILABLESPOTS
            FROM WORKOUTSESSIONS
            WHERE AVAILABLESPOTS > 0
        """)
        workout_sessions = cursor.fetchall()

        if request.method == "POST":
            session_id = request.form.get("session_id")
            if session_id:
                # Dupa ce sesiunea a fost aleasa, redirectam utilizatorul catre pagina de selectare a antrenorului
                return redirect(url_for('select_trainer', session_id=session_id))

        cursor.close()
        return render_template("select_workout.html", workout_sessions=workout_sessions)

    except Exception as e:
        flash(f"An error occurred: {str(e)}", "danger")
        return redirect(url_for("profile"))

@app.route("/select_trainer", methods=["GET", "POST"])
def select_trainer():
    if "user_id" not in session:
        flash("Please log in first.", "danger")
        return redirect(url_for("login"))

    user_id = session["user_id"]
    session_id = request.args.get("session_id")
    trainers = []

    if not session_id:
        flash("No workout session selected.", "danger")
        return redirect(url_for("select_workout"))

    try:
        cursor = conn.cursor()

        # Obtine antrenorii disponibili pentru sesiunea aleasa
        cursor.execute("""
            SELECT t.TRAINERID, t.TRAINER_NAME
            FROM TRAINERS t
            JOIN WORKOUTSESSIONS ws ON t.TRAINERID = ws.TRAINERID
            WHERE ws.SESSIONID = :session_id AND t.TRAINER_STATUS = 'Available'
        """, {"session_id": session_id})
        trainers = cursor.fetchall()

        if request.method == "POST":
            trainer_id = request.form.get("trainer_id")
            if trainer_id:
                # Actualizeaza locurile disponibile in WORKOUTSESSIONS
                cursor.execute("""
                    UPDATE WORKOUTSESSIONS
                    SET AVAILABLESPOTS = AVAILABLESPOTS - 1
                    WHERE SESSIONID = :session_id
                """, {"session_id": session_id})

                # Adauga planificarea în baza de date
                cursor.execute("""
                    INSERT INTO PLANNED_WORKOUTS (CUSTOMERID, TRAINERID, WORKOUTTYPE, SESSIONDATE)
                    VALUES (:user_id, :trainer_id, (SELECT SESSIONNAME FROM WORKOUTSESSIONS WHERE SESSIONID = :session_id), 
                            (SELECT DATEOFSESSION FROM WORKOUTSESSIONS WHERE SESSIONID = :session_id))
                """, {"user_id": user_id, "trainer_id": trainer_id, "session_id": session_id})

                conn.commit()

                flash("Workout session successfully planned!", "success")
                return redirect(url_for("profile"))

        cursor.close()
        return render_template("select_trainer.html", trainers=trainers, session_id=session_id)

    except Exception as e:
        flash(f"An error occurred: {str(e)}", "danger")
        return redirect(url_for("select_workout"))


    except Exception as e:
        flash(f"An error occurred: {str(e)}", "danger")
        return redirect(url_for("profile"))

if __name__ == '__main__':
    app.run(debug=True)
