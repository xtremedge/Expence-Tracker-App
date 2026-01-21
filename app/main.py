from fastapi import FastAPI, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from database import SessionLocal, engine
from models import Base, User, Expense
from auth import hash_password, verify_password, create_access_token, decode_token
from fastapi.responses import StreamingResponse
import csv
from io import StringIO

Base.metadata.create_all(bind=engine)

app = FastAPI()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_current_user(token: str = Header(...), db: Session = Depends(get_db)):
    user_id = decode_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user

#  AUTH

@app.post("/register")
def register(email: str, password: str, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=400, detail="Email already exists")
    user = User(email=email, hashed_password=hash_password(password))
    db.add(user)
    db.commit()
    return {"message": "User registered"}

@app.post("/login")
def login(email: str, password: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token(user.id)
    return {"access_token": token}

# EXPENSE CRUD

@app.post("/expenses")
def add_expense(
    title: str,
    amount: float,
    category: str = None,
    merchant: str = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    expense = Expense(
        title=title,
        amount=amount,
        category=category,
        merchant=merchant,
        user_id=user.id
    )
    db.add(expense)
    db.commit()
    return {"message": "Expense added"}

@app.get("/expenses")
def get_expenses(
    sort_by: str = "date",
    order: str = "desc",
    category: str = None,
    merchant: str = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    query = db.query(Expense).filter(Expense.user_id == user.id)

    if category:
        query = query.filter(Expense.category == category)
    if merchant:
        query = query.filter(Expense.merchant == merchant)

    if sort_by == "amount":
        query = query.order_by(Expense.amount.desc() if order == "desc" else Expense.amount.asc())
    else:
        query = query.order_by(Expense.created_at.desc())

    return query.all()

@app.delete("/expenses/{expense_id}")
def delete_expense(
    expense_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    expense = db.query(Expense).filter(
        Expense.id == expense_id,
        Expense.user_id == user.id
    ).first()

    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")

    db.delete(expense)
    db.commit()
    return {"message": "Deleted"}

# Update Expense Solution

@app.put("/expenses/{expense_id}")
def update_expense(
    expense_id: int,
    title: str = None,
    amount: float = None,
    category: str = None,
    merchant: str = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    expense = db.query(Expense).filter(
        Expense.id == expense_id,
        Expense.user_id == user.id
    ).first()

    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")

    if title is not None:
        expense.title = title
    if amount is not None:
        expense.amount = amount
    if category is not None:
        expense.category = category
    if merchant is not None:
        expense.merchant = merchant

    db.commit()
    return {"message": "Expense updated"}

#  STATISTICS

@app.get("/expenses/stats")
def stats(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    expenses = db.query(Expense).filter(Expense.user_id == user.id).all()
    total = sum(e.amount for e in expenses)
    avg = total / len(expenses) if expenses else 0
    top3 = sorted(expenses, key=lambda x: x.amount, reverse=True)[:3]

    return {
        "total_spending": total,
        "average_spending": avg,
        "top_3_expenses": top3
    }

# EXPORT CSV

@app.get("/expenses/export")
def export_csv(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    expenses = db.query(Expense).filter(Expense.user_id == user.id).all()

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["Title", "Amount", "Category", "Merchant", "Date"])

    for e in expenses:
        writer.writerow([e.title, e.amount, e.category, e.merchant, e.created_at])

    output.seek(0)
    return StreamingResponse(output, media_type="text/csv")
