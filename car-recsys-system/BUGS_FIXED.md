# Bugs Fixed - Favorite Functionality

## 🐛 Issues Identified

### 1. **Backend: get_favorites() chỉ query table `used_vehicles`**
**File:** `backend/app/api/v1/interactions.py`

**Problem:**
```python
# OLD CODE - CHỈ QUERY USED_VEHICLES
vehicle = db.query(Vehicle).filter(Vehicle.vehicle_id == fav.vehicle_id).first()
# Vehicle model = raw.used_vehicles table only
```

Khi user favorite xe từ `raw.new_vehicles`, backend không tìm thấy → `vehicle = None` → skip → favorites page trống!

**Solution:**
```python
# NEW CODE - UNION CẢ 2 TABLES
vehicle_query = text("""
    SELECT vehicle_id, title, brand, ...
    FROM raw.used_vehicles WHERE vehicle_id = :vid
    UNION ALL
    SELECT vehicle_id, title, brand, ...
    FROM raw.new_vehicles WHERE vehicle_id = :vid
    LIMIT 1
""")
```

---

### 2. **Backend: search endpoint chỉ trả xe used**
**File:** `backend/app/api/v1/search.py`

**Problem:**
```python
# OLD CODE
FROM raw.used_vehicles v
WHERE {where_clause}
```

Browse Inventory page chỉ hiển thị used vehicles, new vehicles không có.

**Solution:**
```python
# NEW CODE - UNION QUERY
SELECT ... FROM (
    SELECT ... FROM raw.used_vehicles v WHERE {where_clause}
    UNION ALL
    SELECT ... FROM raw.new_vehicles v WHERE {where_clause}
) combined
```

---

### 3. **Frontend: Favorite button có thể bị che bởi gradient overlay**
**File:** `frontend/src/components/VehicleCard.tsx`

**Problem:**
```tsx
<button className="absolute top-3 right-3 w-9 h-9 ...">
```

Không có z-index → button có thể nằm dưới image overlay → không click được.

**Solution:**
```tsx
<button className="absolute top-3 right-3 z-10 w-9 h-9 ...">
```

---

### 4. **Frontend: FavoritesPage pass sai prop**
**File:** `frontend/src/pages/FavoritesPage.tsx`

**Problem:**
```tsx
<VehicleCard vehicle={favorite} />
// favorite = { id, user_id, vehicle_id, vehicle: {...} }
// VehicleCard expects vehicle object
```

**Solution:**
```tsx
<VehicleCard vehicle={favorite.vehicle as any} />
```

---

## ✅ Testing Checklist

Sau khi restart backend:

```bash
docker-compose restart backend
```

Test các scenarios:

1. ✅ **Add favorite từ used vehicle**
   - Click ♥ button
   - Check favorites page hiển thị xe
   
2. ✅ **Add favorite từ new vehicle**
   - Search "condition:new"
   - Click ♥ button
   - Check favorites page hiển thị xe new

3. ✅ **Remove favorite**
   - Click ♥ đã fill
   - Xe biến mất khỏi favorites page

4. ✅ **Browse Inventory shows both**
   - Search không filter
   - Thấy cả used và new vehicles

5. ✅ **Favorite button clickable**
   - Hover và click ♥ button
   - Button phải respond

---

## 📝 Root Cause Analysis

**Tại sao có 2 tables riêng?**
- Data source khác nhau: `used_vehicles.csv` và `new_vehicles.csv`
- Schema giống nhau nhưng data separated
- ETL pipeline load riêng từng file

**Tại sao không merge?**
- Keep raw data integrity
- Easy to re-process từ source
- Business logic có thể cần phân biệt used vs new

**Long-term solution:**
1. Create unified view: `CREATE VIEW all_vehicles AS SELECT ... FROM used_vehicles UNION ALL SELECT ... FROM new_vehicles`
2. Or use SQLAlchemy polymorphic queries
3. Or add `vehicle_type` column và merge tables

---

## 🔧 Files Modified

1. `backend/app/api/v1/interactions.py` - get_favorites() UNION query
2. `backend/app/api/v1/search.py` - search UNION query
3. `frontend/src/components/VehicleCard.tsx` - z-10 for button
4. `frontend/src/pages/FavoritesPage.tsx` - pass favorite.vehicle
5. `frontend/src/hooks/useApi.ts` - add options param to hooks
6. `frontend/src/components/FeaturedVehicles.tsx` - smart recommendations

---

## 🚀 Additional Improvements

### Smart Recommendations
Khi user click vào xe, system tự động:
1. Store `vehicle_id` trong localStorage
2. Home page fetch similar vehicles based on last click
3. Show "You Might Also Like" instead of generic featured

**Implementation:**
- VehicleCard: `localStorage.setItem('lastClickedVehicle', vehicle_id)`
- FeaturedVehicles: `useSimilarVehicles()` nếu có clicked vehicle
- Fallback to `usePopularVehicles()` nếu chưa click
