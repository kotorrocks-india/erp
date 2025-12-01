"""
Operations Tab - Publish/Delete/Archive UI
"""

import streamlit as st
from models.context import Context
from sqlalchemy.engine import Engine
from services.operations_service import OperationsService
from ui.components import UIComponents
from config import Messages


class OperationsTab:
    """Handles the Operations tab UI"""
    
    def __init__(self, ctx: Context, engine: Engine, operations_service: OperationsService):
        self.ctx = ctx
        self.engine = engine
        self.operations_service = operations_service
    
    def render(self):
        """Render operations tab"""
        st.header("📤 Timetable Operations")
        st.caption("Publish, Archive, Delete, or Duplicate timetables")
        
        # Get metadata
        metadata = self.operations_service.get_timetable_metadata(self.ctx)
        
        if not metadata:
            st.warning("No timetable found for this context")
            return
        
        # Display current status
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Status", metadata.status.upper())
        with col2:
            st.metric("Slots", "N/A")  # TODO: Count slots
        with col3:
            st.metric("Last Modified", metadata.last_modified_at.strftime("%d/%m"))
        
        st.divider()
        
        # Operations section
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.subheader("✅ Publish")
            st.write("Make timetable official and notify stakeholders")
            
            reason = st.text_input("Reason for publishing", key='publish_reason')
            
            if st.button("📢 Publish Timetable", type='primary'):
                if not reason:
                    st.error("Please provide a reason")
                else:
                    # Validate first
                    is_valid, errors = self.operations_service.validate_before_publish(self.ctx)
                    
                    if not is_valid:
                        st.error("Cannot publish: " + ", ".join(errors))
                    else:
                        try:
                            self.operations_service.publish_timetable(
                                self.ctx, 
                                actor='user',  # TODO: Get from session
                                reason=reason
                            )
                            st.success(Messages.PUBLISH_SUCCESS)
                            st.rerun()
                        except Exception as e:
                            st.error(f"Publish failed: {e}")
        
        with col2:
            st.subheader("📦 Archive")
            st.write("Move timetable to archive (read-only)")
            
            archive_reason = st.text_input("Reason for archiving", key='archive_reason')
            
            if st.button("📦 Archive Timetable"):
                if UIComponents.confirm_action("This will make the timetable read-only", "archive"):
                    try:
                        self.operations_service.archive_timetable(
                            self.ctx,
                            actor='user',
                            reason=archive_reason
                        )
                        st.success(Messages.ARCHIVE_SUCCESS)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Archive failed: {e}")
        
        with col3:
            st.subheader("🗑️ Delete")
            st.write("Permanently delete timetable")
            
            st.warning("⚠️ This action cannot be undone!")
            
            delete_reason = st.text_input("Reason for deletion", key='delete_reason')
            
            if st.button("🗑️ Delete Timetable", type='secondary'):
                if not delete_reason:
                    st.error("Please provide a reason for deletion")
                elif UIComponents.confirm_action("This will PERMANENTLY delete ALL data", "delete"):
                    try:
                        self.operations_service.delete_timetable(
                            self.ctx,
                            actor='user',
                            reason=delete_reason,
                            confirm=True
                        )
                        st.success(Messages.DELETE_SUCCESS)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Delete failed: {e}")
        
        st.divider()
        
        # Duplicate section
        st.subheader("📋 Duplicate Timetable")
        st.write("Copy this timetable to another context")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            target_year = st.number_input("Target Year", 1, 5, self.ctx.year)
        with col2:
            target_term = st.number_input("Target Term", 1, 2, self.ctx.term)
        with col3:
            target_div = st.selectbox("Target Division", ['A', 'B', 'C'], 
                                     index=['A', 'B', 'C'].index(self.ctx.division) if self.ctx.division else 0)
        
        if st.button("📋 Duplicate Timetable"):
            # TODO: Build target context
            st.info("Duplicate functionality coming soon")
