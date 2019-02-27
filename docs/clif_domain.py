# -*- coding: utf-8 -*-
#
# Sphinx domain for documenting compiler intermediate representations.
#
# This defines a 'clif' Sphinx domain with the following directives and roles:
#
# .. clif::type:: type
#     Document an IR type.
# .. clif:inst:: v0, v1 = inst op0, op1
#     Document an IR instruction.
#
from __future__ import absolute_import

import re

from docutils import nodes
from docutils.parsers.rst import directives

from sphinx import addnodes
from sphinx.directives import ObjectDescription
from sphinx.domains import Domain, ObjType
from sphinx.locale import l_
from sphinx.roles import XRefRole
from sphinx.util.docfields import Field, GroupedField, TypedField
from sphinx.util.nodes import make_refnode

import sphinx.ext.autodoc


class ClifObject(ObjectDescription):
    """
    Any kind of Cranelift IR object.

    This is a shared base class for the different kinds of indexable objects
    in the Cranelift IR reference.
    """
    option_spec = {
        'noindex': directives.flag,
        'module': directives.unchanged,
        'annotation': directives.unchanged,
    }

    def add_target_and_index(self, name, sig, signode):
        """
        Add ``name`` to the index.

        :param name: The object name returned by :func:`handle_signature`.
        :param sig: The signature text.
        :param signode: The output node.
        """
        targetname = self.objtype + '-' + name
        if targetname not in self.state.document.ids:
            signode['names'].append(targetname)
            signode['ids'].append(targetname)
            signode['first'] = (not self.names)
            self.state.document.note_explicit_target(signode)
            inv = self.env.domaindata['clif']['objects']
            if name in inv:
                self.state_machine.reporter.warning(
                    'duplicate Cranelift object description of %s, ' % name +
                    'other instance in ' + self.env.doc2path(inv[name][0]),
                    line=self.lineno)
            inv[name] = (self.env.docname, self.objtype)

        indextext = self.get_index_text(name)
        if indextext:
            self.indexnode['entries'].append(('single', indextext,
                                              targetname, '', None))


# Type variables are indicated as %T.
typevar = re.compile('(\%[A-Z])')


def parse_type(name, signode):
    """
    Parse a type with embedded type vars and append to signode.

    Return a string that can be compiled into a regular expression matching
    the type.
    """

    re_str = ''

    for part in typevar.split(name):
        if part == '':
            continue
        if len(part) == 2 and part[0] == '%':
            # This is a type parameter. Don't display the %, use emphasis
            # instead.
            part = part[1]
            signode += nodes.emphasis(part, part)
            re_str += r'\w+'
        else:
            signode += addnodes.desc_name(part, part)
            re_str += re.escape(part)
    return re_str


class ClifType(ClifObject):
    """A Cranelift IR type description."""

    def handle_signature(self, sig, signode):
        """
        Parse type signature in ``sig`` and append description to signode.

        Return a global object name for ``add_target_and_index``.
        """

        name = sig.strip()
        parse_type(name, signode)
        return name

    def get_index_text(self, name):
        return name + ' (IR type)'


sep_equal = re.compile('\s*=\s*')
sep_comma = re.compile('\s*,\s*')


def parse_params(s, signode):
    for i, p in enumerate(sep_comma.split(s)):
        if i != 0:
            signode += nodes.Text(', ')
        signode += nodes.emphasis(p, p)


class ClifInst(ClifObject):
    """A Cranelift IR instruction."""

    doc_field_types = [
        TypedField('argument', label=l_('Arguments'),
                   names=('in', 'arg'),
                   typerolename='type', typenames=('type',)),
        TypedField('result', label=l_('Results'),
                   names=('out', 'result'),
                   typerolename='type', typenames=('type',)),
        GroupedField(
            'typevar', names=('typevar',), label=l_('Type Variables')),
        GroupedField('flag', names=('flag',), label=l_('Flags')),
        Field('resulttype', label=l_('Result type'), has_arg=False,
              names=('rtype',)),
    ]

    def handle_signature(self, sig, signode):
        # Look for signatures like
        #
        #   v0, v1 = foo op0, op1
        #   v0 = foo
        #   foo op0

        parts = re.split(sep_equal, sig, 1)
        if len(parts) == 2:
            # Outgoing parameters.
            parse_params(parts[0], signode)
            signode += nodes.Text(' = ')
            name = parts[1]
        else:
            name = parts[0]

        # Parse 'name arg, arg'
        parts = name.split(None, 1)
        name = parts[0]
        signode += addnodes.desc_name(name, name)

        if len(parts) == 2:
            # Incoming parameters.
            signode += nodes.Text(' ')
            parse_params(parts[1], signode)

        return name

    def get_index_text(self, name):
        return name


class ClifInstGroup(ClifObject):
    """A Cranelift IR instruction group."""


class CraneliftDomain(Domain):
    """Cranelift domain for IR objects."""
    name = 'clif'
    label = 'Cranelift'

    object_types = {
        'type': ObjType(l_('type'), 'type'),
        'inst': ObjType(l_('instruction'), 'inst')
    }

    directives = {
        'type': ClifType,
        'inst': ClifInst,
        'instgroup': ClifInstGroup,
    }

    roles = {
        'type': XRefRole(),
        'inst': XRefRole(),
        'instgroup': XRefRole(),
    }

    initial_data = {
        'objects': {},  # fullname -> docname, objtype
    }

    def clear_doc(self, docname):
        for fullname, (fn, _l) in list(self.data['objects'].items()):
            if fn == docname:
                del self.data['objects'][fullname]

    def merge_domaindata(self, docnames, otherdata):
        for fullname, (fn, objtype) in otherdata['objects'].items():
            if fn in docnames:
                self.data['objects'][fullname] = (fn, objtype)

    def resolve_xref(self, env, fromdocname, builder, typ, target, node,
                     contnode):
        objects = self.data['objects']
        if target not in objects:
            return None
        obj = objects[target]
        return make_refnode(builder, fromdocname, obj[0],
                            obj[1] + '-' + target, contnode, target)

    def resolve_any_xref(self, env, fromdocname, builder, target,
                         node, contnode):
        objects = self.data['objects']
        if target not in objects:
            return []
        obj = objects[target]
        return [('clif:' + self.role_for_objtype(obj[1]),
                 make_refnode(builder, fromdocname, obj[0],
                              obj[1] + '-' + target, contnode, target))]


class TypeDocumenter(sphinx.ext.autodoc.Documenter):
    # Invoke with .. autocliftype::
    objtype = 'cliftype'
    # Convert into clif:type directives
    domain = 'clif'
    directivetype = 'type'

    @classmethod
    def can_document_member(cls, member, membername, isattr, parent):
        return False

    def resolve_name(self, modname, parents, path, base):
        return 'base.types', [base]

    def add_content(self, more_content, no_docstring=False):
        super(TypeDocumenter, self).add_content(more_content, no_docstring)
        sourcename = self.get_sourcename()
        membytes = self.object.membytes
        if membytes:
            self.add_line(u':bytes: {}'.format(membytes), sourcename)
        else:
            self.add_line(u':bytes: Can\'t be stored in memory', sourcename)


class InstDocumenter(sphinx.ext.autodoc.Documenter):
    # Invoke with .. autoinst::
    objtype = 'inst'
    # Convert into clif:inst directives
    domain = 'clif'
    directivetype = 'inst'

    @classmethod
    def can_document_member(cls, member, membername, isattr, parent):
        return False

    def resolve_name(self, modname, parents, path, base):
        if path:
            return path.rstrip('.'), [base]
        else:
            return 'base.instructions', [base]

    def format_signature(self):
        inst = self.object
        sig = inst.name
        if len(inst.outs) > 0:
            sig = ', '.join([op.name for op in inst.outs]) + ' = ' + sig
        if len(inst.ins) > 0:
            op = inst.ins[0]
            sig += ' ' + op.name
            # If the first input is variable-args, this is 'return'. No parens.
            if op.kind.name == 'variable_args':
                sig += '...'.format(op.name)
            for op in inst.ins[1:]:
                # This is a call or branch with args in (...).
                if op.kind.name == 'variable_args':
                    sig += '({}...)'.format(op.name)
                else:
                    sig += ', ' + op.name
        return sig

    def add_directive_header(self, sig):
        """Add the directive header and options to the generated content."""
        domain = getattr(self, 'domain', 'clif')
        directive = getattr(self, 'directivetype', self.objtype)
        sourcename = self.get_sourcename()
        self.add_line(u'.. %s:%s:: %s' % (domain, directive, sig), sourcename)
        if self.options.noindex:
            self.add_line(u'   :noindex:', sourcename)

    def add_content(self, more_content, no_docstring=False):
        super(InstDocumenter, self).add_content(more_content, no_docstring)
        sourcename = self.get_sourcename()
        inst = self.object

        # Add inputs and outputs.
        for op in inst.ins:
            if op.is_value():
                typ = op.typevar
            else:
                typ = op.kind
            self.add_line(u':in {} {}: {}'.format(
                typ, op.name, op.get_doc()), sourcename)
        for op in inst.outs:
            if op.is_value():
                typ = op.typevar
            else:
                typ = op.kind
            self.add_line(u':out {} {}: {}'.format(
                typ, op.name, op.get_doc()), sourcename)

        # Document type inference for polymorphic instructions.
        if inst.is_polymorphic:
            if inst.ctrl_typevar is not None:
                if inst.use_typevar_operand:
                    tvopnum = inst.value_opnums[inst.format.typevar_operand]
                    self.add_line(
                            u':typevar {}: inferred from {}'
                            .format(
                                inst.ctrl_typevar.name,
                                inst.ins[tvopnum]),
                            sourcename)
                else:
                    self.add_line(
                            u':typevar {}: explicitly provided'
                            .format(inst.ctrl_typevar.name),
                            sourcename)
            for tv in inst.other_typevars:
                self.add_line(
                        u':typevar {}: from input operand'.format(tv.name),
                        sourcename)


class InstGroupDocumenter(sphinx.ext.autodoc.ModuleLevelDocumenter):
    # Invoke with .. autoinstgroup::
    objtype = 'instgroup'
    # Convert into clif:instgroup directives
    domain = 'clif'
    directivetype = 'instgroup'

    @classmethod
    def can_document_member(cls, member, membername, isattr, parent):
        return False

    def format_name(self):
        return "{}.{}".format(self.modname, ".".join(self.objpath))

    def add_content(self, more_content, no_docstring=False):
        super(InstGroupDocumenter, self).add_content(
                more_content, no_docstring)
        sourcename = self.get_sourcename()
        indexed = self.env.domaindata['clif']['objects']

        names = [inst.name for inst in self.object.instructions]
        names.sort()
        for name in names:
            if name in indexed:
                self.add_line(u':clif:inst:`{}`'.format(name), sourcename)
            else:
                self.add_line(u'``{}``'.format(name), sourcename)


def setup(app):
    app.add_domain(CraneliftDomain)
    app.add_autodocumenter(TypeDocumenter)
    app.add_autodocumenter(InstDocumenter)
    app.add_autodocumenter(InstGroupDocumenter)

    return {'version': '0.1'}
