"""
Institution Rooms Schema
Integrated with weekly_subject_distribution for room assignment
"""

from __future__ import annotations
from sqlalchemy import text as sa_text
from sqlalchemy.engine import Engine
from core.schema_registry import register
import logging

log = logging.getLogger(__name__)

def _exec(conn, sql):
    conn.execute(sa_text(sql))

@register
def install_institution_rooms_schema(engine: Engine):
    """
    Schema for managing institution rooms/venues
    Plugs directly into weekly_subject_distribution via room_code
    """
    with engine.begin() as conn:
        
        # =================================================================
        # 1. ROOM MASTER TABLE
        # =================================================================
        _exec(conn, """
            CREATE TABLE IF NOT EXISTS institution_rooms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                
                -- Room Identification
                room_code TEXT NOT NULL UNIQUE COLLATE NOCASE,
                room_name TEXT NOT NULL,
                building_name TEXT,
                floor_number TEXT,
                
                -- Room Type & Capacity
                room_type TEXT DEFAULT 'classroom', 
                -- Options: 'classroom', 'lab', 'workshop', 'auditorium', 
                --          'seminar_hall', 'tutorial_room', 'studio', 'other'
                
                seating_capacity INTEGER DEFAULT 0,
                exam_capacity INTEGER DEFAULT 0,
                
                -- Facilities
                has_projector INTEGER DEFAULT 0,
                has_smartboard INTEGER DEFAULT 0,
                has_ac INTEGER DEFAULT 0,
                has_audio_system INTEGER DEFAULT 0,
                has_computers INTEGER DEFAULT 0,
                computer_count INTEGER DEFAULT 0,
                has_lab_equipment INTEGER DEFAULT 0,
                
                -- Availability
                is_available_for_timetable INTEGER DEFAULT 1,
                is_available_for_exams INTEGER DEFAULT 1,
                
                -- Context
                campus_location TEXT,
                department_code TEXT,
                
                -- Notes
                special_notes TEXT,
                facility_details TEXT, -- JSON for additional facilities
                
                -- Status
                active INTEGER DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        _exec(conn, """
            CREATE INDEX IF NOT EXISTS idx_rooms_type 
            ON institution_rooms(room_type, active)
        """)
        
        _exec(conn, """
            CREATE INDEX IF NOT EXISTS idx_rooms_capacity 
            ON institution_rooms(seating_capacity)
        """)
        
        _exec(conn, """
            CREATE INDEX IF NOT EXISTS idx_rooms_dept 
            ON institution_rooms(department_code, active)
        """)
        
        # =================================================================
        # 2. ROOM BOOKINGS/ALLOCATIONS (Optional - for tracking)
        # =================================================================
        _exec(conn, """
            CREATE TABLE IF NOT EXISTS room_bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                
                room_code TEXT NOT NULL,
                
                -- Time Slot
                ay_label TEXT NOT NULL,
                degree_code TEXT,
                year INTEGER,
                term INTEGER,
                division_code TEXT,
                
                day_of_week INTEGER NOT NULL, -- 1=Mon, 6=Sat
                period_index INTEGER NOT NULL,
                
                -- Usage
                booking_type TEXT DEFAULT 'timetable', 
                -- Options: 'timetable', 'exam', 'event', 'maintenance', 'blocked'
                
                subject_code TEXT,
                offering_id INTEGER,
                distribution_id INTEGER,
                
                -- Module dates (if applicable)
                effective_start_date DATE,
                effective_end_date DATE,
                
                -- Details
                booked_by TEXT,
                booking_reason TEXT,
                
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                
                FOREIGN KEY (room_code) REFERENCES institution_rooms(room_code),
                FOREIGN KEY (offering_id) REFERENCES subject_offerings(id),
                FOREIGN KEY (distribution_id) REFERENCES weekly_subject_distribution(id)
            )
        """)
        
        _exec(conn, """
            CREATE INDEX IF NOT EXISTS idx_room_bookings_slot
            ON room_bookings(room_code, day_of_week, period_index, ay_label)
        """)
        
        _exec(conn, """
            CREATE INDEX IF NOT EXISTS idx_room_bookings_subject
            ON room_bookings(subject_code, ay_label, term)
        """)
        
        # =================================================================
        # 3. ROOM AVAILABILITY RULES (Optional - for constraints)
        # =================================================================
        _exec(conn, """
            CREATE TABLE IF NOT EXISTS room_availability_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                
                room_code TEXT NOT NULL,
                
                -- Time constraints
                day_of_week INTEGER, -- NULL = all days
                period_index INTEGER, -- NULL = all periods
                
                -- Availability
                is_available INTEGER DEFAULT 1,
                
                -- Context (when rule applies)
                ay_label TEXT,
                term INTEGER,
                
                -- Reason
                unavailability_reason TEXT,
                
                -- Validity
                valid_from DATE,
                valid_to DATE,
                
                active INTEGER DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                
                FOREIGN KEY (room_code) REFERENCES institution_rooms(room_code)
            )
        """)
        
        _exec(conn, """
            CREATE INDEX IF NOT EXISTS idx_room_availability
            ON room_availability_rules(room_code, day_of_week, period_index, active)
        """)
        
        # =================================================================
        # 4. VIEWS FOR EASY QUERYING
        # =================================================================
        
        # View: Available rooms for timetabling
        _exec(conn, "DROP VIEW IF EXISTS v_available_timetable_rooms")
        _exec(conn, """
            CREATE VIEW v_available_timetable_rooms AS
            SELECT 
                room_code,
                room_name,
                building_name,
                room_type,
                seating_capacity,
                exam_capacity,
                has_projector,
                has_smartboard,
                has_ac,
                has_computers,
                computer_count,
                campus_location,
                department_code
            FROM institution_rooms
            WHERE active = 1 
            AND is_available_for_timetable = 1
            ORDER BY building_name, room_code
        """)
        
        # View: Room utilization summary
        _exec(conn, "DROP VIEW IF EXISTS v_room_utilization")
        _exec(conn, """
            CREATE VIEW v_room_utilization AS
            SELECT 
                r.room_code,
                r.room_name,
                r.room_type,
                r.seating_capacity,
                COUNT(DISTINCT rb.id) as total_bookings,
                COUNT(DISTINCT CASE WHEN rb.booking_type = 'timetable' THEN rb.id END) as timetable_slots,
                COUNT(DISTINCT CASE WHEN rb.booking_type = 'exam' THEN rb.id END) as exam_slots
            FROM institution_rooms r
            LEFT JOIN room_bookings rb ON rb.room_code = r.room_code
            WHERE r.active = 1
            GROUP BY r.room_code, r.room_name, r.room_type, r.seating_capacity
        """)
        
        # View: Room conflicts detection
        _exec(conn, "DROP VIEW IF EXISTS v_room_conflicts")
        _exec(conn, """
            CREATE VIEW v_room_conflicts AS
            SELECT 
                rb1.room_code,
                rb1.ay_label,
                rb1.day_of_week,
                rb1.period_index,
                rb1.subject_code as subject_1,
                rb2.subject_code as subject_2,
                rb1.division_code as division_1,
                rb2.division_code as division_2
            FROM room_bookings rb1
            JOIN room_bookings rb2 
                ON rb1.room_code = rb2.room_code
                AND rb1.ay_label = rb2.ay_label
                AND rb1.day_of_week = rb2.day_of_week
                AND rb1.period_index = rb2.period_index
                AND rb1.id < rb2.id
            WHERE rb1.booking_type = 'timetable' 
            AND rb2.booking_type = 'timetable'
        """)
        
        log.info("✅ Institution Rooms Schema Installed (Complete)")
