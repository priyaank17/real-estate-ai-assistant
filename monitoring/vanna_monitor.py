"""
Vanna 2.0 Monitoring and Logging Setup

Provides comprehensive logging and monitoring for:
- Agent execution
- Tool calls
- SQL queries
- Errors and performance metrics
"""
import logging
import time
from datetime import datetime
from typing import Optional, Dict, Any
from pathlib import Path


class VannaMonitor:
    """
    Centralized monitoring for Vanna agent.
    
    Tracks:
    - Query execution times
    - Tool usage
    - SQL generation success/failure
    - Errors and exceptions
    """
    
    def __init__(self, log_file: Optional[str] = None):
        """
        Initialize monitor.
        
        Args:
            log_file: Optional path to log file. If None, logs to console only.
        """
        self.log_file = log_file
        self.stats = {
            'total_queries': 0,
            'successful_queries': 0,
            'failed_queries': 0,
            'total_sql_generated': 0,
            'total_tool_calls': 0,
            'tool_usage': {},
            'avg_response_time': 0.0,
            'total_response_time': 0.0
        }
        
        # Setup logging
        self.logger = logging.getLogger('vanna_monitor')
        self.logger.setLevel(logging.INFO)
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        console_handler.setFormatter(console_formatter)
        self.logger.addHandler(console_handler)
        
        # File handler (if specified)
        if log_file:
            Path(log_file).parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(log_file)
            file_handler.setLevel(logging.DEBUG)
            file_formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            file_handler.setFormatter(file_formatter)
            self.logger.addHandler(file_handler)
    
    def log_query_start(self, user_id: str, query: str, conversation_id: str) -> Dict[str, Any]:
        """Log the start of a query."""
        query_context = {
            'user_id': user_id,
            'query': query,
            'conversation_id': conversation_id,
            'start_time': time.time(),
            'timestamp': datetime.now().isoformat()
        }
        
        self.logger.info(f"🚀 Query started | User: {user_id} | Conv: {conversation_id}")
        self.logger.info(f"   Query: {query[:100]}{'...' if len(query) > 100 else ''}")
        
        self.stats['total_queries'] += 1
        
        return query_context
    
    def log_query_end(self, query_context: Dict[str, Any], success: bool, response: Optional[str] = None, error: Optional[str] = None):
        """Log the end of a query."""
        duration = time.time() - query_context['start_time']
        
        self.stats['total_response_time'] += duration
        self.stats['avg_response_time'] = self.stats['total_response_time'] / self.stats['total_queries']
        
        if success:
            self.stats['successful_queries'] += 1
            self.logger.info(f"✅ Query completed | Duration: {duration:.2f}s")
            if response:
                self.logger.debug(f"   Response: {response[:200]}...")
        else:
            self.stats['failed_queries'] += 1
            self.logger.error(f"❌ Query failed | Duration: {duration:.2f}s")
            if error:
                self.logger.error(f"   Error: {error}")
    
    def log_sql_generation(self, sql: str, success: bool):
        """Log SQL generation."""
        self.stats['total_sql_generated'] += 1
        
        if success:
            self.logger.info(f"🔍 SQL Generated: {sql[:150]}{'...' if len(sql) > 150 else ''}")
        else:
            self.logger.warning(f"⚠️  SQL Generation failed")
    
    def log_tool_call(self, tool_name: str, args: Dict[str, Any], success: bool):
        """Log tool execution."""
        self.stats['total_tool_calls'] += 1
        
        if tool_name not in self.stats['tool_usage']:
            self.stats['tool_usage'][tool_name] = 0
        self.stats['tool_usage'][tool_name] += 1
        
        status = "✅" if success else "❌"
        self.logger.info(f"{status} Tool: {tool_name} | Args: {str(args)[:100]}")
    
    def log_error(self, error: Exception, context: Optional[Dict[str, Any]] = None):
        """Log an error."""
        self.logger.error(f"💥 Error: {type(error).__name__}: {str(error)}")
        if context:
            self.logger.error(f"   Context: {context}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get current monitoring stats."""
        return {
            **self.stats,
            'success_rate': (
                self.stats['successful_queries'] / self.stats['total_queries'] * 100
                if self.stats['total_queries'] > 0 else 0
            )
        }
    
    def print_stats(self):
        """Print current stats to console."""
        stats = self.get_stats()
        
        print("\n" + "=" * 60)
        print("VANNA AGENT MONITORING STATS")
        print("=" * 60)
        print(f"Total Queries:        {stats['total_queries']}")
        print(f"Successful:           {stats['successful_queries']}")
        print(f"Failed:               {stats['failed_queries']}")
        print(f"Success Rate:         {stats['success_rate']:.1f}%")
        print(f"SQL Generated:        {stats['total_sql_generated']}")
        print(f"Total Tool Calls:     {stats['total_tool_calls']}")
        print(f"Avg Response Time:    {stats['avg_response_time']:.2f}s")
        print()
        print("Tool Usage:")
        for tool, count in stats['tool_usage'].items():
            print(f"  - {tool}: {count}")
        print("=" * 60 + "\n")


# Global monitor instance
_monitor = None

def get_monitor(log_file: Optional[str] = None) -> VannaMonitor:
    """Get or create global monitor instance."""
    global _monitor
    if _monitor is None:
        _monitor = VannaMonitor(log_file=log_file or "logs/vanna_monitor.log")
    return _monitor
