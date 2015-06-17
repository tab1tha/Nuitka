#     Copyright 2015, Kay Hayen, mailto:kay.hayen@gmail.com
#
#     Part of "Nuitka", an optimizing Python compiler that is compatible and
#     integrates with CPython, but also works on its own.
#
#     Licensed under the Apache License, Version 2.0 (the "License");
#     you may not use this file except in compliance with the License.
#     You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#     Unless required by applicable law or agreed to in writing, software
#     distributed under the License is distributed on an "AS IS" BASIS,
#     WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#     See the License for the specific language governing permissions and
#     limitations under the License.
#
""" Loop nodes.

There are for and loop nodes, but both are reduced to loops with break/continue
statements for it. These re-formulations require that optimization of loops has
to be very general, yet the node type for loop, becomes very simple.
"""

from nuitka.optimizations.TraceCollections import ConstraintCollectionBranch

from .Checkers import checkStatementsSequenceOrNone
from .NodeBases import NodeBase, StatementChildrenHavingBase


class StatementLoop(StatementChildrenHavingBase):
    kind = "STATEMENT_LOOP"

    named_children = (
        "body",
    )

    checkers = {
        "body" : checkStatementsSequenceOrNone
    }

    def __init__(self, body, source_ref):
        StatementChildrenHavingBase.__init__(
            self,
            values     = {
                "body" : body
            },
            source_ref = source_ref
        )

        # For code generation, so it knows if an exit target is needed.
        self.has_break = False

    getLoopBody = StatementChildrenHavingBase.childGetter("body")
    setLoopBody = StatementChildrenHavingBase.childSetter("body")

    def mayReturn(self):
        loop_body = self.getLoopBody()

        if loop_body is not None and loop_body.mayReturn():
            return True

        return False

    def mayBreak(self):
        # The loop itself may never break another loop.
        return False

    def mayContinue(self):
        # The loop itself may never continue another loop.
        return False

    def isStatementAborting(self):
        loop_body = self.getLoopBody()

        if loop_body is None:
            return True
        else:
            return not loop_body.mayBreak()

    def computeStatement(self, constraint_collection):
        outer_constraint_collection = constraint_collection
        constraint_collection = ConstraintCollectionBranch(
            parent = constraint_collection,
            name   = "loop"
        )

        abort_context = constraint_collection.makeAbortStackContext(
            catch_breaks    = True,
            catch_continues = True,
            catch_returns   = False
        )

        with abort_context:
            loop_body = self.getLoopBody()

            if loop_body is not None:
                # Look ahead. what will be written and degrade about that.
                constraint_collection.degradePartiallyFromCode(loop_body)

                result = loop_body.computeStatementsSequence(
                    constraint_collection = constraint_collection
                )

                # Might be changed.
                if result is not loop_body:
                    self.setLoopBody(result)
                    loop_body = result

            # If we break, the outer collections becomes a merge of all those breaks
            # or just the one, if there is only one.
            break_collections = constraint_collection.getLoopBreakCollections()

        # Consider trailing "continue" statements, these have no effect, so we
        # can remove them.
        if loop_body is not None:
            assert loop_body.isStatementsSequence()

            statements = loop_body.getStatements()
            assert statements # Cannot be empty

            # If the last statement is a "continue" statement, it can simply
            # be discarded.
            last_statement = statements[-1]
            if last_statement.isStatementContinueLoop():
                if len(statements) == 1:
                    self.setLoopBody(None)
                    loop_body = None
                else:
                    last_statement.replaceWith(None)

                constraint_collection.signalChange(
                    "new_statements",
                    last_statement.getSourceReference(),
                    """\
Removed useless terminal 'continue' as last statement of loop."""
                )


        if break_collections:
            outer_constraint_collection.mergeMultipleBranches(break_collections)

        # Consider leading "break" statements, they should be the only, and
        # should lead to removing the whole loop statement. Trailing "break"
        # statements could also be handled, but that would need to consider if
        # there are other "break" statements too. Numbering loop exits is
        # nothing we have yet.
        if loop_body is not None:
            assert loop_body.isStatementsSequence()

            statements = loop_body.getStatements()
            assert statements # Cannot be empty

            if len(statements) == 1 and statements[-1].isStatementBreakLoop():
                return None, "new_statements", """\
Removed useless loop with immediate 'break' statement."""

        return self, None, None


class StatementContinueLoop(NodeBase):
    kind = "STATEMENT_CONTINUE_LOOP"

    def __init__(self, source_ref):
        NodeBase.__init__(self, source_ref = source_ref)

    def isStatementAborting(self):
        return True

    def mayRaiseException(self, exception_type):
        return False

    def mayContinue(self):
        return True

    def computeStatement(self, constraint_collection):
        # This statement being aborting, will already tell everything.
        constraint_collection.onLoopContinue()

        return self, None, None


class StatementBreakLoop(NodeBase):
    kind = "STATEMENT_BREAK_LOOP"

    def __init__(self, source_ref):
        NodeBase.__init__(self, source_ref = source_ref)

    def isStatementAborting(self):
        return True

    def mayRaiseException(self, exception_type):
        return False

    def mayBreak(self):
        return True

    def computeStatement(self, constraint_collection):
        # This statement being aborting, will already tell everything.
        constraint_collection.onLoopBreak()

        return self, None, None
