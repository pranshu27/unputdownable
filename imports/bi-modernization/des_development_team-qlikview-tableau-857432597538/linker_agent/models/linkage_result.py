"""
Data model for complete term-column linkage result
"""
from pydantic import BaseModel, Field
from typing import List, Dict, Any
from datetime import datetime
from pathlib import Path
import json
from .term_column_link import TermColumnLink


class TermColumnLinkageResult(BaseModel):
    """
    Complete result of business term to column linking process.
    
    Contains all links (Tier 1 direct + Tier 2 semantic) and summary statistics.
    
    Attributes:
        links: List of all term-column links
        summary: Dictionary containing statistics and metadata
    """
    
    links: List[TermColumnLink] = Field(
        default_factory=list,
        description="List of all term-column links (Tier 1 + Tier 2)"
    )
    summary: Dict[str, Any] = Field(
        default_factory=dict,
        description="Summary statistics and metadata"
    )
    
    def calculate_summary(self, total_terms: int, processing_time_seconds: float = 0.0) -> Dict[str, Any]:
        """
        Calculate summary statistics from the links.
        
        Args:
            total_terms: Total number of business terms processed
            processing_time_seconds: Time taken to process (optional)
            
        Returns:
            Dictionary with summary statistics
        """
        tier1_links = [link for link in self.links if link.linkage_type == "direct"]
        tier2_links = [link for link in self.links if link.linkage_type == "semantic"]
        
        tier1_count = len(tier1_links)
        tier2_count = len(tier2_links)
        linked_count = tier1_count + tier2_count
        unlinked_count = total_terms - linked_count
        
        # Calculate average confidence scores
        avg_tier1_confidence = (
            sum(link.confidence_score for link in tier1_links) / tier1_count
            if tier1_count > 0 else 0.0
        )
        
        avg_tier2_confidence = (
            sum(link.confidence_score for link in tier2_links) / tier2_count
            if tier2_count > 0 else 0.0
        )
        
        overall_avg_confidence = (
            sum(link.confidence_score for link in self.links) / linked_count
            if linked_count > 0 else 0.0
        )
        
        # Calculate linkage coverage
        linkage_coverage = (linked_count / total_terms * 100.0) if total_terms > 0 else 0.0
        
        summary = {
            "total_terms": total_terms,
            "tier1_count": tier1_count,
            "tier2_count": tier2_count,
            "linked_count": linked_count,
            "unlinked_count": unlinked_count,
            "avg_tier1_confidence": round(avg_tier1_confidence, 2),
            "avg_tier2_confidence": round(avg_tier2_confidence, 2),
            "overall_avg_confidence": round(overall_avg_confidence, 2),
            "linkage_coverage": round(linkage_coverage, 2),
            "processing_time_seconds": round(processing_time_seconds, 2),
            "timestamp": datetime.utcnow().isoformat()
        }
        
        self.summary = summary
        return summary
    
    def to_json(self) -> Dict[str, Any]:
        """
        Serialize to JSON-compatible dictionary.
        
        Returns:
            Dictionary representation suitable for JSON serialization
        """
        return {
            "links": [link.model_dump() for link in self.links],
            "summary": self.summary
        }
    
    def get_tier1_links(self) -> List[TermColumnLink]:
        """Get all Tier 1 (direct) links"""
        return [link for link in self.links if link.linkage_type == "direct"]
    
    def get_tier2_links(self) -> List[TermColumnLink]:
        """Get all Tier 2 (semantic) links"""
        return [link for link in self.links if link.linkage_type == "semantic"]
    
    def get_high_confidence_links(self, threshold: float = 80.0) -> List[TermColumnLink]:
        """Get all links with confidence >= threshold"""
        return [link for link in self.links if link.confidence_score >= threshold]
    
    def get_links_by_term_id(self, term_id: int) -> List[TermColumnLink]:
        """Get all links for a specific term ID"""
        return [link for link in self.links if link.term_id == term_id]
    
    def sort_links_by_confidence(self, descending: bool = True) -> None:
        """Sort links by confidence score"""
        self.links.sort(key=lambda x: x.confidence_score, reverse=descending)
    
    def __str__(self) -> str:
        """Human-readable string representation"""
        tier1_count = len(self.get_tier1_links())
        tier2_count = len(self.get_tier2_links())
        total = len(self.links)
        coverage = self.summary.get('linkage_coverage', 0.0)
        
        return (
            f"TermColumnLinkageResult("
            f"total_links={total}, "
            f"tier1={tier1_count}, "
            f"tier2={tier2_count}, "
            f"coverage={coverage:.1f}%)"
        )
    
    def __repr__(self) -> str:
        """Developer-friendly representation"""
        return self.__str__()
    
    def print_summary(self) -> None:
        """Print a formatted summary to console"""
        print("\n" + "=" * 80)
        print("ALATION TERM-COLUMN LINKAGE SUMMARY")
        print("=" * 80)
        
        if self.summary:
            print(f"Total Terms:           {self.summary.get('total_terms', 0)}")
            print(f"Linked Terms:          {self.summary.get('linked_count', 0)}")
            print(f"Unlinked Terms:        {self.summary.get('unlinked_count', 0)}")
            print(f"Linkage Coverage:      {self.summary.get('linkage_coverage', 0):.1f}%")
            print()
            print(f"Tier 1 (Direct):       {self.summary.get('tier1_count', 0)} links")
            print(f"  Avg Confidence:      {self.summary.get('avg_tier1_confidence', 0):.1f}%")
            print(f"Tier 2 (Semantic):     {self.summary.get('tier2_count', 0)} links")
            print(f"  Avg Confidence:      {self.summary.get('avg_tier2_confidence', 0):.1f}%")
            print()
            print(f"Overall Avg Confidence: {self.summary.get('overall_avg_confidence', 0):.1f}%")
            print(f"Processing Time:       {self.summary.get('processing_time_seconds', 0):.2f}s")
            print(f"Timestamp:             {self.summary.get('timestamp', 'N/A')}")
        else:
            print("No summary available. Call calculate_summary() first.")
        
        print("=" * 80 + "\n")
    
    def save_to_file(self, filepath: str) -> None:
        """
        Save linkage result to JSON file.
        
        Args:
            filepath: Path to output JSON file
        """
        # Create directory if it doesn't exist
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
        
        # Convert to JSON
        data = self.to_json()
        
        # Write to file
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
    
    @classmethod
    def load_from_file(cls, filepath: str) -> 'TermColumnLinkageResult':
        """
        Load linkage result from JSON file.
        
        Args:
            filepath: Path to input JSON file
            
        Returns:
            TermColumnLinkageResult instance
        """
        with open(filepath, 'r') as f:
            data = json.load(f)
        
        # Convert links back to TermColumnLink objects
        links = [TermColumnLink(**link_data) for link_data in data.get('links', [])]
        
        return cls(
            links=links,
            summary=data.get('summary', {})
        )
