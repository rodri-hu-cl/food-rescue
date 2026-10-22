# Food Rescue — AI-Assisted Recipe Recommendation

An AI-assisted recipe recommendation tool designed for university students in shared accommodation. It matches available ingredients, prioritizes "Use Soon" perishables, filters by cooking-time limits, and enforces safety guardrails.

## 1. Setup Instructions

1. **Clone the repository:**

   ```bash
   git clone https://github.com/rodri-hu-cl/food-rescue.git
   cd food-rescue
   ```

2. **Create and activate a virtual environment:**

   ```bash
   python -m venv venv
   ```

   On macOS/Linux:

   ```bash
   source venv/bin/activate
   ```

   On Windows:

   ```bash
   venv\Scripts\activate
   ```

3. **Install dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

4. **Configure your API Key:**

   Copy `.env.example` to `.env`:

   On macOS/Linux:

   ```bash
   cp .env.example .env
   ```

   On Windows:

   ```bash
   copy .env.example .env
   ```

   Open `.env` and paste your Alibaba Cloud Bailian API Key.

---

## 2. How to Run the Core Workflow

Run the main demo script:

```bash
python src/app.py
```

*(Or if using Streamlit: `streamlit run src/app.py`)*

---

## 3. How to Check Results (Verification)

### Test Case 1: Standard Priority Match

- **Input:**
  - Ingredients: `eggs`, `spinach`, `cheddar`
  - Marked Use Soon: `spinach`
  - Max Time: `15 minutes`

- **Expected Output:**
  - System selects a fast egg/spinach dish (e.g., *Spinach & Cheese Omelet*).
  - Applies a `1.5x` score boost to spinach.
  - Formats a clear card showing:
    - **In Kitchen:** Eggs, Spinach, Cheddar
    - **Missing / Optional:** Butter, Salt, Pepper
    - **Step-by-step instructions:** No more than 15 minutes.

### Test Case 2: Safety Refusal (Guardrail Check)

- **Input:** `["chicken", "bleach"]`
- **Expected Output:** System refuses to process and returns safety warning: *"Bleach is a dangerous non-food item."*